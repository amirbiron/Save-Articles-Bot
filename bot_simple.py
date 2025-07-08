import logging
import sqlite3
import re
from datetime import datetime
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# טעינת משתני סביבה
load_dotenv()

# הגדרות
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# הגדרות קבועות מהסביבה
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "read_later_simple.db"

if not TELEGRAM_TOKEN:
    print("❌ שגיאה: TELEGRAM_TOKEN לא הוגדר ב-.env")
    exit(1)

class SimpleBot:
    def __init__(self):
        self.init_database()
        print("✅ בוט פשוט מוכן!")
        
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
                category TEXT DEFAULT 'כללי',
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        print("✅ מסד נתונים מוכן!")
    
    def extract_simple_content(self, url: str) -> Optional[Dict]:
        """הוצאת תוכן פשוט מכתבה"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            print(f"🔄 מנסה לטעון: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # מחפש כותרת
            title = None
            for selector in ['h1', 'title']:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.get_text().strip():
                    title = title_elem.get_text().strip()
                    break
            
            # מחפש תוכן
            text = ""
            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            
            if title and text and len(text) > 50:
                print(f"✅ תוכן נמצא: {title[:50]}...")
                return {
                    'title': title[:200],
                    'text': text[:2000],
                    'success': True
                }
            else:
                print("❌ לא נמצא תוכן מספיק")
                return None
                
        except Exception as e:
            print(f"❌ שגיאה: {str(e)}")
            return None
    
    def simple_summary(self, text: str) -> str:
        """סיכום פשוט"""
        sentences = text.split('.')[:2]  # שני משפטים ראשונים
        summary = '. '.join(sentences).strip()
        if len(summary) > 150:
            summary = summary[:150] + "..."
        return summary or "לא ניתן ליצור סיכום"
    
    def save_article(self, user_id: int, url: str, title: str, summary: str) -> int:
        """שמירת כתבה"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO articles (user_id, url, title, summary)
            VALUES (?, ?, ?, ?)
        ''', (user_id, url, title, summary))
        article_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return article_id
    
    def get_articles(self, user_id: int) -> List:
        """קבלת כתבות"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE user_id = ? ORDER BY date_saved DESC LIMIT 10', (user_id,))
        articles = cursor.fetchall()
        conn.close()
        return articles
    
    def delete_article(self, article_id: int, user_id: int):
        """מחיקת כתבה"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        conn.commit()
        conn.close()

# יצירת הבוט
bot = SimpleBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת התחלה"""
    print(f"👤 משתמש חדש התחיל: {update.effective_user.id}")
    
    welcome_message = """
🤖 שלום! זה הבוט "שמור לי לקרוא אחר כך"

📝 **איך זה עובד:**
• שלח לי קישור לכתבה - אני אשמור אותה לך
• שלח /saved - לראות כתבות שמורות  
• שלח /help - לעזרה

נסה לשלוח לי קישור לכתבה! 🚀
"""
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """עזרה"""
    print(f"❓ עזרה התבקש על ידי: {update.effective_user.id}")
    
    help_text = """
🆘 **עזרה:**

🔗 **שלח קישור** - הבוט ישמור את הכתבה
📚 **/saved** - רשימת כתבות שמורות
❓ **/help** - הודעה זו

**דוגמה:**
שלח: https://www.ynet.co.il/articles/0,7340,L-12345,00.html
"""
    await update.message.reply_text(help_text)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקישורים"""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    print(f"🔗 קישור התקבל מ-{user_id}: {url}")
    
    # בדיקת URL
    if not re.match(r'https?://', url):
        await update.message.reply_text("❌ זה לא נראה כמו קישור תקין. נסה שוב!")
        return
    
    # הודעת טעינה
    loading_msg = await update.message.reply_text("⏳ מעבד את הכתבה...")
    
    # חילוץ תוכן
    article_data = bot.extract_simple_content(url)
    
    if not article_data:
        await loading_msg.edit_text("❌ לא הצלחתי לטעון את הכתבה. נסה קישור אחר!")
        return
    
    # יצירת סיכום
    summary = bot.simple_summary(article_data['text'])
    
    # שמירה
    article_id = bot.save_article(user_id, url, article_data['title'], summary)
    
    # כפתור מחיקה
    keyboard = [[InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    response = f"""
✅ **כתבה נשמרה!**

📰 **כותרת:** {article_data['title']}

📝 **סיכום:** {summary}

🔗 [קישור לכתבה]({url})
"""
    
    await loading_msg.edit_text(response, reply_markup=reply_markup, parse_mode='Markdown')
    print(f"✅ כתבה נשמרה עבור {user_id}")

async def saved_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """כתבות שמורות"""
    user_id = update.effective_user.id
    print(f"📚 בקשת כתבות שמורות מ-{user_id}")
    
    articles = bot.get_articles(user_id)
    
    if not articles:
        await update.message.reply_text("📭 אין כתבות שמורות עדיין. שלח קישור כדי להתחיל!")
        return
    
    response = f"📚 **הכתבות שלך** ({len(articles)} כתבות):\n\n"
    
    for i, article in enumerate(articles, 1):
        title = article[3][:50] + "..." if len(article[3]) > 50 else article[3]
        date = article[6][:10]  # רק התאריך
        response += f"{i}. 📰 {title}\n📅 {date}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בכפתורים"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data.startswith("delete_"):
        article_id = int(data.split("_")[1])
        bot.delete_article(article_id, user_id)
        await query.edit_message_text("🗑️ הכתבה נמחקה!")
        print(f"🗑️ כתבה {article_id} נמחקה עבור {user_id}")

def main():
    """הפעלת הבוט"""
    print("🚀 מתחיל בוט פשוט...")
    print(f"🔑 טוקן: {TELEGRAM_TOKEN[:10]}...")
    
    # יצירת האפליקציה
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # הוספת handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("saved", saved_articles))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("✅ הכל מוכן!")
    print("📡 מתחיל לקבל הודעות...")
    
    # הפעלה
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()