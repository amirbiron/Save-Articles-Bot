import logging
import sqlite3
import json
import re
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
import asyncio
import aiohttp
from dataclasses import dataclass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ספריות חיצוניות נדרשות
try:
    from newspaper import Article
    import openai
    from transformers import pipeline
except ImportError:
    print("נדרשות ספריות נוספות: pip install newspaper3k openai transformers torch")

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
        if use_openai:
            openai.api_key = OPENAI_API_KEY
        # הסרנו את HuggingFace summarizer כי PyTorch יקר מדי
        
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
        """הוצאת תוכן מכתבה באמצעות Newspaper3k"""
        try:
            # נסה עם User-Agent כדי לא להיחסם
            article = Article(url, language='he')
            article.config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            article.config.request_timeout = 10
            
            article.download()
            article.parse()
            
            # אם לא מצאנו תוכן בעברית, ננסה באנגלית
            if not article.text.strip():
                article = Article(url, language='en')
                article.config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                article.download()
                article.parse()
            
            if not article.text.strip():
                logger.error(f"No content found for URL: {url}")
                return None
                
            return {
                'title': article.title or 'כותרת לא זמינה',
                'text': article.text,
                'authors': article.authors,
                'publish_date': article.publish_date
            }
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {str(e)}")
            # נחזיר פרטי השגיאה לצורך debug
            return {'error': str(e), 'url': url}
    
    def extract_content_fallback(self, url: str) -> Optional[Dict]:
        """שיטה חלופית להוצאת תוכן"""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # חפש כותרת
            title = None
            for selector in ['h1', 'title', '.headline', '.title']:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.get_text().strip():
                    title = title_elem.get_text().strip()
                    break
            
            # חפש תוכן
            text = ""
            for selector in ['article', '.content', '.article-body', 'main', '.post-content']:
                content_elem = soup.select_one(selector)
                if content_elem:
                    text = content_elem.get_text().strip()
                    break
            
            if not text:
                # אם לא מצאנו, קח את כל הפסקאות
                paragraphs = soup.find_all('p')
                text = '\n'.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            
            if title and text:
                return {
                    'title': title[:200],  # הגבל אורך כותרת
                    'text': text[:5000],   # הגבל אורך טקסט
                    'authors': [],
                    'publish_date': None
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Fallback extraction failed for {url}: {str(e)}")
            return None
    
    def summarize_text(self, text: str, max_length: int = 150) -> str:
        """סיכום טקסט באמצעות AI"""
        try:
            if self.use_openai:
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "אתה מסכם כתבות בעברית. צור סיכום קצר וחד של הכתבה."},
                        {"role": "user", "content": f"סכם את הכתבה הזו: {text[:3000]}"}
                    ],
                    max_tokens=max_length,
                    temperature=0.3
                )
                return response.choices[0].message.content
            else:
                # סיכום פשוט ללא HuggingFace
                sentences = text.split('.')[:3]  # 3 משפטים ראשונים
                summary = '. '.join(sentences).strip()
                if len(summary) > max_length:
                    summary = summary[:max_length] + "..."
                return summary or "סיכום לא זמין"
                
        except Exception as e:
            logger.error(f"שגיאה בסיכום: {e}")
            return "סיכום לא זמין"
    
    def detect_category(self, title: str, text: str) -> str:
        """זיהוי קטגוריה אוטומטי"""
        categories = {
            'טכנולוגיה': ['טכנולוגיה', 'אפליקציה', 'סמארטפון', 'מחשב', 'אינטרנט', 'סייבר', 'AI', 'בינה מלאכותית'],
            'בריאות': ['בריאות', 'רפואה', 'מחקר', 'טיפול', 'תזונה', 'ספורט', 'כושר'],
            'כלכלה': ['כלכלה', 'כספים', 'השקעות', 'בורסה', 'עסקים', 'חברה', 'סטארטאפ'],
            'פוליטיקה': ['פוליטיקה', 'ממשלה', 'כנסת', 'בחירות', 'מדינה', 'חוק'],
            'השראה': ['השראה', 'מוטיבציה', 'אישיות', 'הצלחה', 'חלומות', 'מטרות']
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
            cursor.execute('''
                SELECT id, url, title, summary, full_text, category, tags, date_saved, user_id 
                FROM articles WHERE user_id = ? AND category = ?
                ORDER BY date_saved DESC
            ''', (user_id, category))
        else:
            cursor.execute('''
                SELECT id, url, title, summary, full_text, category, tags, date_saved, user_id 
                FROM articles WHERE user_id = ?
                ORDER BY date_saved DESC
            ''', (user_id,))
        
        articles = []
        for row in cursor.fetchall():
            articles.append(SavedArticle(*row))
        
        conn.close()
        return articles
    
    def update_article_category(self, article_id: int, category: str, tags: str = None):
        """עדכון קטגוריה ותגיות"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if tags:
            cursor.execute('''
                UPDATE articles SET category = ?, tags = ? WHERE id = ?
            ''', (category, tags, article_id))
        else:
            cursor.execute('''
                UPDATE articles SET category = ? WHERE id = ?
            ''', (category, article_id))
        
        conn.commit()
        conn.close()
    
    def delete_article(self, article_id: int, user_id: int):
        """מחיקת כתבה"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM articles WHERE id = ? AND user_id = ?
        ''', (article_id, user_id))
        
        conn.commit()
        conn.close()
    
    def export_articles(self, user_id: int, format_type: str = 'json') -> str:
        """יצוא כתבות לגיבוי"""
        articles = self.get_user_articles(user_id)
        
        if format_type == 'json':
            data = []
            for article in articles:
                data.append({
                    'title': article.title,
                    'url': article.url,
                    'summary': article.summary,
                    'category': article.category,
                    'tags': article.tags,
                    'date_saved': article.date_saved
                })
            return json.dumps(data, ensure_ascii=False, indent=2)
        
        else:  # text format
            text = "הכתבות השמורות שלי:\n\n"
            for article in articles:
                # חילוץ תאריך בלי שעה
                date_only = article.date_saved.split(' ')[0]  # לוקח רק החלק לפני הרווח
                
                text += f"📰 {article.title}\n"
                text += f"🔗 {article.url}\n"
                text += f"📂 {article.category}\n"
                text += f"📅 {date_only}\n"
                text += f"📝 {article.summary}\n\n"
                text += "─" * 50 + "\n\n"
            
            return text

# הגדרת הבוט
bot = ReadLaterBot(use_openai=False)  # שנה ל-True אם יש לך OpenAI API key

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

🔸 **שליחת קישור**: פשוט שלח קישור לכתבה ואני אשמור אותה אוטומטית
🔸 **/saved** - צפייה בכל הכתבות השמורות שלך
🔸 **/backup** - גיבוי טקסט נח לקריאה (או `/backup json` לקובץ טכני)
🔸 **/tag [מספר] [קטגוריה] [תגית]** - עדכון קטגוריה ותגיות
   דוגמה: /tag 3 AI חשוב

📂 **קטגוריות אוטומטיות**:
• טכנולוגיה • בריאות • כלכלה • פוליטיקה • השראה • כללי
"""
    await update.message.reply_text(help_text)



async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקישורים"""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    # בדיקה שזה אכן קישור
    if not re.match(r'https?://', url):
        await update.message.reply_text("אנא שלח קישור תקין (מתחיל ב-http או https)")
        return
    
    # הודעת טעינה
    loading_message = await update.message.reply_text("🔄 מעבד את הכתבה...")
    
    # הוצאת תוכן
    article_data = bot.extract_article_content(url)
    
    # אם יש שגיאה, נציג אותה
    if article_data and 'error' in article_data:
        error_msg = f"❌ שגיאה בטעינת הכתבה:\n{article_data['error']}\n\nננסה שיטה אחרת..."
        await loading_message.edit_text(error_msg)
        
        # נסה שיטה חלופית
        article_data = bot.extract_content_fallback(url)
    
    if not article_data or 'error' in article_data:
        error_details = ""
        if article_data and 'error' in article_data:
            error_details = f"\n\nפרטי השגיאה: {article_data['error']}"
        
        await loading_message.edit_text(
            f"❌ מצטער, לא הצלחתי לטעון את הכתבה הזו.\n\n"
            f"🔗 קישור: {url}\n"
            f"💡 נסה:\n"
            f"• לבדוק שהקישור תקין\n"
            f"• לנסות כתבה מאתר אחר\n"
            f"• לשלוח קישור ישיר לכתבה (לא לעמוד הבית)"
            f"{error_details}"
        )
        return
    
    # סיכום התוכן
    await loading_message.edit_text("🤖 מכין סיכום...")
    summary = bot.summarize_text(article_data['text'])
    
    # זיהוי קטגוריה
    category = bot.detect_category(article_data['title'], article_data['text'])
    
    # שמירה במסד נתונים
    article_id = bot.save_article(
        user_id=user_id,
        url=url,
        title=article_data['title'],
        summary=summary,
        full_text=article_data['text'],
        category=category
    )
    
    # הכנת תגובה עם כפתורים
    keyboard = [
        [
            InlineKeyboardButton("📂 שנה קטגוריה", callback_data=f"change_category_{article_id}"),
            InlineKeyboardButton("🔍 הצג מלא", callback_data=f"show_full_{article_id}")
        ],
        [
            InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # הצגת מידע על הכתבה
    article_info = ""
    if article_data.get('authors'):
        article_info += f"✍️ **כותב**: {', '.join(article_data['authors'])}\n"
    if article_data.get('publish_date'):
        article_info += f"📅 **תאריך**: {article_data['publish_date']}\n"
    
    response_text = f"""
✅ **הכתבה נשמרה בהצלחה!**

📰 **כותרת**: {article_data['title']}
📂 **קטגוריה**: {category}
{article_info}
📝 **סיכום**:
{summary}

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
    
    # קיבוץ לפי קטגוריות
    categories = {}
    for article in articles:
        if article.category not in categories:
            categories[article.category] = []
        categories[article.category].append(article)
    
    response = "📚 **הכתבות השמורות שלך:**\n\n"
    
    for category, cat_articles in categories.items():
        response += f"📂 **{category}** ({len(cat_articles)} כתבות)\n"
        for i, article in enumerate(cat_articles[:5], 1):  # הצג רק 5 ראשונות
            response += f"{i}. {article.title[:60]}{'...' if len(article.title) > 60 else ''}\n"
        
        if len(cat_articles) > 5:
            response += f"   ... ועוד {len(cat_articles) - 5} כתבות\n"
        response += "\n"
    
    # הוספת כפתורים לפעולות
    keyboard = [
        [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")],
        [InlineKeyboardButton("💾 גיבוי", callback_data="backup")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בלחיצות על כפתורים"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("show_full_"):
        article_id = int(data.split("_")[2])
        # הצגת טקסט מלא (מקוצר)
        await query.edit_message_text("🔍 התכונה הזו בפיתוח...")
        
    elif data.startswith("delete_"):
        article_id = int(data.split("_")[1])
        bot.delete_article(article_id, user_id)
        await query.edit_message_text("🗑️ הכתבה נמחקה בהצלחה")
        
    elif data == "backup":
        # יצירת גיבוי
        backup_data = bot.export_articles(user_id, 'json')
        
        # שמירת הקובץ
        filename = f"backup_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(backup_data)
        
        await query.edit_message_text("💾 הגיבוי מוכן! הקובץ נשמר בשרת.")
        
    elif data == "stats":
        articles = bot.get_user_articles(user_id)
        categories = {}
        for article in articles:
            categories[article.category] = categories.get(article.category, 0) + 1
        
        stats_text = f"📊 **הסטטיסטיקות שלך:**\n\n"
        stats_text += f"📚 סה\"כ כתבות: {len(articles)}\n\n"
        
        for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            stats_text += f"📂 {category}: {count} כתבות\n"
        
        await query.edit_message_text(stats_text, parse_mode='Markdown')

async def tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת תיוג"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("שימוש: /tag [מספר_כתבה] [קטגוריה] [תגית_אופציונלית]")
        return
    
    try:
        article_id = int(context.args[0])
        category = context.args[1]
        tags = ' '.join(context.args[2:]) if len(context.args) > 2 else ''
        
        bot.update_article_category(article_id, category, tags)
        await update.message.reply_text(f"✅ הכתבה עודכנה: קטגוריה '{category}'{f', תגיות: {tags}' if tags else ''}")
        
    except ValueError:
        await update.message.reply_text("❌ מספר הכתבה חייב להיות מספר")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {str(e)}")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת גיבוי"""
    user_id = update.effective_user.id
    articles = bot.get_user_articles(user_id)
    
    if not articles:
        await update.message.reply_text("אין לך כתבות שמורות לגיבוי. שלח לי קישור כדי להתחיל! 📚")
        return
    
    # בדיקה איזה פורמט התבקש
    format_type = 'text'  # ברירת מחדל - טקסט נח לקריאה
    if context.args and context.args[0].lower() == 'json':
        format_type = 'json'
    
    # יצירת גיבוי
    backup_data = bot.export_articles(user_id, format_type)
    
    # שמירת הקובץ
    file_extension = 'txt' if format_type == 'text' else 'json'
    filename = f"backup_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(backup_data)
        
        # שליחת הקובץ למשתמש
        with open(filename, 'rb') as f:
            display_filename = f"כתבות_שמורות_{datetime.now().strftime('%Y-%m-%d')}.{file_extension}"
            format_desc = "קובץ טקסט נח לקריאה" if format_type == 'text' else "קובץ JSON טכני"
            
            await update.message.reply_document(
                document=f,
                filename=display_filename,
                caption=f"💾 **גיבוי הכתבות שלך** ({format_desc})\n\n📚 {len(articles)} כתבות\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n💡 לגיבוי JSON טכני השתמש: `/backup json`"
            )
        
        # מחיקת הקובץ הזמני
        os.remove(filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה ביצירת הגיבוי: {str(e)}")

def main():
    """הפעלת הבוט"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # הוספת handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saved", saved_articles))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("tag", tag_command))
    
    # טיפול בקישורים
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # טיפול בכפתורים
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 הבוט מופעל במצב polling...")
    print("📱 פקודת /saved אמורה לעבוד עכשיו!")
    
    # הפעלת הבוט עם Polling (לפיתוח מקומי)
    application.run_polling()

# Flask routes הוסרו - הבוט עובד במצב polling

if __name__ == '__main__':
    main()
