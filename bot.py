import logging
import sqlite3
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
import os
import asyncio
from flask import Flask, request
from dataclasses import dataclass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ספריות חיצוניות נדרשות
try:
    from newspaper import Article
    import openai
except ImportError:
    print("נדרשות ספריות נוספות: pip install newspaper3k openai")

# הגדרות
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# הגדרות קבועות
TELEGRAM_TOKEN = "7560439844:AAEEVJwLFO44j7QoxZNULRlYlZMKeRK3yP0"
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"  # אופציונלי
DB_PATH = "read_later.db"

@dataclass
class SavedArticle:
    id: int
    url: str
    title: str
    summary: str
    full_text: str
    category: str
    tags: str
    date_saved: str
    user_id: int

class ReadLaterBot:
    def __init__(self, use_openai: bool = False):
        self.use_openai = use_openai
        self.init_database()
        
    def init_database(self):
        """יצירת מסד נתונים"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                full_text TEXT NOT NULL,
                category TEXT DEFAULT 'כללי',
                tags TEXT DEFAULT '',
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def extract_article_content(self, url: str) -> Optional[Dict]:
        """הוצאת תוכן מכתבה"""
        try:
            article = Article(url, language='he')
            article.config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            article.config.request_timeout = 10
            
            article.download()
            article.parse()
            
            if not article.text.strip():
                article = Article(url, language='en')
                article.config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                article.download()
                article.parse()
            
            if not article.text.strip():
                return None
                
            return {
                'title': article.title or 'כותרת לא זמינה',
                'text': article.text,
                'authors': article.authors,
                'publish_date': article.publish_date
            }
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {str(e)}")
            return {'error': str(e), 'url': url}
    
    def extract_content_fallback(self, url: str) -> Optional[Dict]:
        """שיטה חלופית להוצאת תוכן"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title = None
            for selector in ['h1', 'title', '.headline', '.title']:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.get_text().strip():
                    title = title_elem.get_text().strip()
                    break
            
            text = ""
            for selector in ['article', '.content', '.article-body', 'main']:
                content_elem = soup.select_one(selector)
                if content_elem:
                    text = content_elem.get_text().strip()
                    break
            
            if not text:
                paragraphs = soup.find_all('p')
                text = '\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            
            if title and text:
                return {'title': title[:200], 'text': text[:5000], 'authors': [], 'publish_date': None}
            
            return None
            
        except Exception as e:
            logger.error(f"Fallback extraction failed for {url}: {str(e)}")
            return None
    
    def summarize_text(self, text: str, max_length: int = 150) -> str:
        """סיכום טקסט"""
        try:
            sentences = text.split('.')[:3]
            summary = '. '.join(sentences).strip()
            if len(summary) > max_length:
                summary = summary[:max_length] + "..."
            return summary or "סיכום לא זמין"
        except:
            return "סיכום לא זמין"
    
    def detect_category(self, title: str, text: str) -> str:
        """זיהוי קטגוריה אוטומטי"""
        categories = {
            'טכנולוגיה': ['טכנולוגיה', 'אפליקציה', 'סמארטפון', 'מחשב', 'אינטרנט', 'AI'],
            'בריאות': ['בריאות', 'רפואה', 'מחקר', 'טיפול', 'תזונה'],
            'כלכלה': ['כלכלה', 'כספים', 'השקעות', 'בורסה', 'עסקים'],
            'פוליטיקה': ['פוליטיקה', 'ממשלה', 'כנסת', 'בחירות'],
            'השראה': ['השראה', 'מוטיבציה', 'אישיות', 'הצלחה']
        }
        
        full_text = f"{title} {text}".lower()
        for category, keywords in categories.items():
            if any(keyword.lower() in full_text for keyword in keywords):
                return category
        return 'כללי'
    
    def save_article(self, user_id: int, url: str, title: str, summary: str, 
                    full_text: str, category: str = 'כללי', tags: str = '') -> int:
        """שמירת כתבה במסד נתונים"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO articles (user_id, url, title, summary, full_text, category, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, url, title, summary, full_text, category, tags))
        article_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return article_id
    
    def get_user_articles(self, user_id: int, category: str = None) -> List[SavedArticle]:
        """שליפת כתבות של משתמש"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if category:
            cursor.execute('SELECT * FROM articles WHERE user_id = ? AND category = ? ORDER BY date_saved DESC', (user_id, category))
        else:
            cursor.execute('SELECT * FROM articles WHERE user_id = ? ORDER BY date_saved DESC', (user_id,))
        
        articles = [SavedArticle(*row) for row in cursor.fetchall()]
        conn.close()
        return articles
    
    def delete_article(self, article_id: int, user_id: int):
        """מחיקת כתבה"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        conn.commit()
        conn.close()

# הגדרת הבוט
bot = ReadLaterBot(use_openai=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת התחלה"""
    welcome_message = """
📚 שלום וברוך הבא ל"שמור לי לקרוא אחר כך"! 

🔸 שלח לי קישור לכתבה, ואני אסכם ואשמור אותה לך במקום מסודר.
🔸 השתמש ב-/saved כדי לראות את כל הכתבות שלך
🔸 השתמש ב-/help לעזרה נוספת

קדימה, שלח לי קישור לכתבה מעניינת! 🚀
"""
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת עזרה"""
    help_text = """
📖 איך להשתמש בבוט:

🔸 **שליחת קישור**: פשוט שלח קישור לכתבה
🔸 **/saved** - צפייה בכל הכתבות השמורות
🔸 **/help** - הצגת הודעת עזרה זו

📂 **קטגוריות אוטומטיות**:
• טכנולוגיה • בריאות • כלכלה • פוליטיקה • השראה • כללי
"""
    await update.message.reply_text(help_text)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקישורים"""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not re.match(r'https?://', url):
        await update.message.reply_text("אנא שלח קישור תקין (מתחיל ב-http או https)")
        return
    
    loading_message = await update.message.reply_text("🔄 מעבד את הכתבה...")
    
    article_data = bot.extract_article_content(url)
    
    if article_data and 'error' in article_data:
        await loading_message.edit_text("🔄 ננסה שיטה אחרת...")
        article_data = bot.extract_content_fallback(url)
    
    if not article_data or 'error' in article_data:
        await loading_message.edit_text(f"❌ מצטער, לא הצלחתי לטעון את הכתבה הזו.\n🔗 {url}")
        return
    
    await loading_message.edit_text("🤖 מכין סיכום...")
    summary = bot.summarize_text(article_data['text'])
    category = bot.detect_category(article_data['title'], article_data['text'])
    
    article_id = bot.save_article(
        user_id=user_id,
        url=url,
        title=article_data['title'],
        summary=summary,
        full_text=article_data['text'],
        category=category
    )
    
    keyboard = [[InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    response_text = f"""
✅ **הכתבה נשמרה בהצלחה!**

📰 **כותרת**: {article_data['title']}
📂 **קטגוריה**: {category}
📝 **סיכום**: {summary}

🔗 **קישור**: {url}
"""
    
    await loading_message.edit_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')

async def saved_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """הצגת כתבות שמורות"""
    user_id = update.effective_user.id
    articles = bot.get_user_articles(user_id)
    
    if not articles:
        await update.message.reply_text("אין לך כתבות שמורות עדיין. שלח לי קישור כדי להתחיל! 📚")
        return
    
    response = f"📚 **הכתבות השמורות שלך** ({len(articles)} כתבות):\n\n"
    
    for i, article in enumerate(articles[:10], 1):
        response += f"{i}. 📰 {article.title[:50]}{'...' if len(article.title) > 50 else ''}\n"
        response += f"   📂 {article.category} | 📅 {article.date_saved[:10]}\n\n"
    
    if len(articles) > 10:
        response += f"... ועוד {len(articles) - 10} כתבות\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בלחיצות על כפתורים"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("delete_"):
        article_id = int(data.split("_")[1])
        bot.delete_article(article_id, user_id)
        await query.edit_message_text("🗑️ הכתבה נמחקה בהצלחה")

# Flask app
app = Flask(__name__)
telegram_app = None

def get_telegram_app():
    """יצירת אפליקציית הטלגרם"""
    global telegram_app
    if telegram_app is None:
        telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # הוספת handlers
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("help", help_command))
        telegram_app.add_handler(CommandHandler("saved", saved_articles))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
        telegram_app.add_handler(CallbackQueryHandler(button_callback))
        
        print("🤖 הבוט הוגדר בהצלחה!")
    
    return telegram_app

@app.route('/webhook', methods=['POST'])
def webhook():
    """קבלת עדכונים מטלגרם"""
    try:
        update_data = request.get_json()
        if update_data:
            app_instance = get_telegram_app()
            update = Update.de_json(update_data, app_instance.bot)
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            async def process_update():
                await app_instance.process_update(update)
            
            loop.run_until_complete(process_update())
            loop.close()
            
        return 'OK'
    except Exception as e:
        print(f"❌ שגיאה ב-webhook: {e}")
        return f'Error: {str(e)}', 500

@app.route('/')
def home():
    return "<h1>🤖 Telegram Read Later Bot</h1><p>Status: ✅ Active</p>"

@app.route('/health')
def health():
    return {"status": "healthy", "bot": "running", "timestamp": datetime.now().isoformat()}

@app.route('/setwebhook')
def set_webhook():
    """הגדרת webhook ידנית"""
    try:
        webhook_url = "https://save-articles-bot.onrender.com/webhook"
        app_instance = get_telegram_app()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def setup_webhook():
            await app_instance.bot.set_webhook(webhook_url)
            return await app_instance.bot.get_webhook_info()
        
        webhook_info = loop.run_until_complete(setup_webhook())
        loop.close()
        
        return {
            "status": "success",
            "webhook_url": webhook_url,
            "webhook_info": {
                "url": webhook_info.url,
                "pending_update_count": webhook_info.pending_update_count,
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 8080))
    
    print("🚀 מתחיל את הבוט...")
    print(f"🌐 Port: {PORT}")
    print(f"🔗 Webhook URL: https://save-articles-bot.onrender.com/webhook")
    
    get_telegram_app()
    app.run(host="0.0.0.0", port=PORT, debug=False)
