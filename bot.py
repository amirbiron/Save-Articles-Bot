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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
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

# מצבי משתמשים (פשוט בזיכרון)
user_states = {}

@dataclass
class SavedArticle:
    id: int
    url: str
    title: str
    summary: str
    full_text: str
    category: str
    tags: str
    keywords: str
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
                keywords TEXT DEFAULT '',
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # הוספת עמודת מילות מפתח לכתבות קיימות
        cursor.execute("PRAGMA table_info(articles)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'keywords' not in columns:
            cursor.execute('ALTER TABLE articles ADD COLUMN keywords TEXT DEFAULT ""')
        
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
    
    def extract_keywords(self, title: str, text: str, max_keywords: int = 8) -> str:
        """חילוץ מילות מפתח עיקריות מהטקסט"""
        try:
            import re
            from collections import Counter
            
            # טקסט מלא לניתוח
            full_text = f"{title} {text}".lower()
            
            # הסרת סימני פיסוק ומספרים
            clean_text = re.sub(r'[^\u0590-\u05FF\w\s]', ' ', full_text)
            
            # חלוקה למילים
            words = clean_text.split()
            
            # מילות עצירה בעברית ואנגלית
            stop_words = {
                'של', 'את', 'על', 'לא', 'זה', 'היא', 'הוא', 'זאת', 'כל', 'אל', 'עם', 'בין', 'גם',
                'אך', 'או', 'כי', 'אם', 'מה', 'מי', 'איך', 'למה', 'מתי', 'איפה', 'הזה', 'הזאת',
                'שלו', 'שלה', 'שלי', 'שלנו', 'שלהם', 'שלהן', 'אני', 'אתה', 'את', 'אנחנו', 'אתם',
                'הם', 'הן', 'יש', 'אין', 'הייה', 'היו', 'יהיה', 'תהיה', 'יהיו', 'תהיינה',
                'the', 'and', 'or', 'but', 'if', 'then', 'else', 'when', 'where', 'why', 'how',
                'what', 'who', 'which', 'that', 'this', 'these', 'those', 'a', 'an', 'is', 'are',
                'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
                'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'cannot'
            }
            
            # סינון מילים קצרות ומילות עצירה
            filtered_words = [
                word for word in words 
                if len(word) >= 3 and word not in stop_words and word.isalpha()
            ]
            
            # ספירת תדירות
            word_counts = Counter(filtered_words)
            
            # חילוץ המילים הנפוצות ביותר
            keywords = [word for word, count in word_counts.most_common(max_keywords)]
            
            return ', '.join(keywords)
            
        except Exception as e:
            logger.error(f"שגיאה בחילוץ מילות מפתח: {e}")
            return ""
    
    def save_article(self, user_id: int, url: str, title: str, summary: str, 
                    full_text: str, category: str = 'כללי', tags: str = '') -> int:
        """שמירת כתבה במסד נתונים"""
        # חילוץ מילות מפתח
        keywords = self.extract_keywords(title, summary)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO articles (user_id, url, title, summary, full_text, category, tags, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, url, title, summary, full_text, category, tags, keywords))
        
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
                SELECT id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id 
                FROM articles WHERE user_id = ? AND category = ?
                ORDER BY date_saved DESC
            ''', (user_id, category))
        else:
            cursor.execute('''
                SELECT id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id 
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
    
    def search_articles(self, user_id: int, search_query: str) -> List[SavedArticle]:
        """חיפוש כתבות לפי מילות מפתח"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # חיפוש בכותרת, סיכום, מילות מפתח ותגיות
        search_terms = search_query.lower().split()
        
        # בניית שאילתת חיפוש
        search_conditions = []
        search_params = []
        
        for term in search_terms:
            search_conditions.append('''
                (LOWER(title) LIKE ? OR 
                 LOWER(summary) LIKE ? OR 
                 LOWER(keywords) LIKE ? OR 
                 LOWER(tags) LIKE ?)
            ''')
            search_params.extend([f'%{term}%', f'%{term}%', f'%{term}%', f'%{term}%'])
        
        # חיבור כל התנאים עם AND
        where_clause = ' AND '.join(search_conditions)
        
        cursor.execute(f'''
            SELECT id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id 
            FROM articles 
            WHERE user_id = ? AND ({where_clause})
            ORDER BY date_saved DESC
        ''', [user_id] + search_params)
        
        articles = []
        for row in cursor.fetchall():
            articles.append(SavedArticle(*row))
        
        conn.close()
        return articles
    
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
                    'keywords': article.keywords,
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
                text += f"� {article.keywords if article.keywords else 'אין מילות מפתח'}\n"
                text += f"� {article.summary}\n\n"
                text += "─" * 50 + "\n\n"
            
            return text

# פונקציה ליצירת מקלדת קבועה
def get_main_keyboard():
    """יצירת מקלדת קבועה עם כפתורי פעולה עיקריים"""
    keyboard = [
        [KeyboardButton("📚 הכתבות שלי"), KeyboardButton("📋 רשימת כתבות")],
        [KeyboardButton("🔍 חיפוש"), KeyboardButton("💾 גיבוי")],
        [KeyboardButton("📊 סטטיסטיקות"), KeyboardButton("❓ עזרה")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# הגדרת הבוט
bot = ReadLaterBot(use_openai=False)  # שנה ל-True אם יש לך OpenAI API key

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת התחלה"""
    welcome_message = """
📚 שלום וברוך הבא ל"שמור לי לקרוא אחר כך"! 

🔸 שלח לי קישור לכתבה, ואני אסכם ואשמור אותה לך במקום מסודר.
🔸 השתמש בכפתורים למטה או שלח קישור ישירות
🔸 לחץ על "🔍 חיפוש" ואז כתוב מילות חיפוש ישירות

קדימה, שלח לי קישור לכתבה מעניינת! 🚀
"""
    await update.message.reply_text(welcome_message, reply_markup=get_main_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת עזרה"""
    help_text = """
📖 איך להשתמש בבוט:

🔸 **שליחת קישור**: פשוט שלח קישור לכתבה ואני אשמור אותה אוטומטית
🔸 **/saved** - צפייה בכל הכתבות השמורות שלך לפי קטגוריות
🔸 **/list** - רשימת כתבות עם מספרים למחיקה מהירה
🔸 **/search [מילים]** - חיפוש כתבות לפי מילות מפתח, כותרת או תוכן
🔸 **/delete [מספר]** - מחיקת כתבה לפי מספר
🔸 **/backup** - גיבוי טקסט נח לקריאה (או `/backup json` לקובץ טכני)
🔸 **/tag [מספר] [קטגוריה] [תגית]** - עדכון קטגוריה ותגיות
   דוגמה: /tag 3 AI חשוב

📂 **קטגוריות אוטומטיות**:
• טכנולוגיה • בריאות • כלכלה • פוליטיקה • השראה • כללי

🔍 **דוגמאות חיפוש**:
• `/search טכנולוגיה AI`
• `/search בריאות תזונה`
• `/search ממשלה`

🗑️ **דרכים למחיקת כתבות**:
• דרך הכפתורים בתצוגת הכתבה
• דרך פקודת `/delete [מספר]` לאחר `/list`
"""
    await update.message.reply_text(help_text)



async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בהודעות טקסט - כפתורים וחיפוש"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # בדיקה אם זה כפתור מהמקלדת הקבועה
    if text == "📚 הכתבות שלי":
        await saved_articles(update, context)
        return
    elif text == "📋 רשימת כתבות":
        await list_command(update, context)
        return
    elif text == "🔍 חיפוש":
        user_states[user_id] = "searching"
        await update.message.reply_text(
            "🔍 **מצב חיפוש פעיל**\n\n"
            "כתוב עכשיו את מילות החיפוש שלך:\n"
            "• דוגמאות: טכנולוגיה AI\n"
            "• או: בריאות תזונה\n"
            "• או: פוליטיקה ממשלה\n\n"
            "💡 אני אחפש בכותרות, סיכומים ומילות מפתח",
            parse_mode='Markdown'
        )
        return
    elif text == "💾 גיבוי":
        await backup_command(update, context)
        return
    elif text == "📊 סטטיסטיקות":
        # נוסיף סטטיסטיקות
        articles = bot.get_user_articles(user_id)
        categories = {}
        for article in articles:
            categories[article.category] = categories.get(article.category, 0) + 1
        
        stats_text = f"📊 **הסטטיסטיקות שלך:**\n\n"
        stats_text += f"📚 סה\"כ כתבות: {len(articles)}\n\n"
        
        for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            stats_text += f"📂 {category}: {count} כתבות\n"
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
        return
    elif text == "❓ עזרה":
        await help_command(update, context)
        return
    
    # בדיקה אם המשתמש במצב חיפוש
    if user_states.get(user_id) == "searching":
        user_states[user_id] = None  # איפוס מצב
        
        # חיפוש כתבות
        found_articles = bot.search_articles(user_id, text)
        
        if not found_articles:
            await update.message.reply_text(
                f"🔍 לא נמצאו כתבות עבור: **{text}**\n\n💡 נסה מילים אחרות או בדוק איות",
                parse_mode='Markdown'
            )
            return
        
        # הצגת תוצאות החיפוש
        response = f"🔍 **תוצאות חיפוש עבור: \"{text}\"**\n\n"
        response += f"נמצאו {len(found_articles)} כתבות:\n\n"
        
        # יצירת כפתורים לכתבות שנמצאו
        keyboard = []
        
        # הצגת עד 8 כתבות ראשונות
        for article in found_articles[:8]:
            button_text = f"📰 {article.title[:30]}{'...' if len(article.title) > 30 else ''}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_article_{article.id}")])
        
        # אם יש יותר מ-8 כתבות
        if len(found_articles) > 8:
            keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(found_articles) - 8} תוצאות", callback_data=f"search_more_{text}")])
        
        # כפתורי ניווט
        keyboard.append([
            InlineKeyboardButton("🔍 חיפוש חדש", callback_data="search"),
            InlineKeyboardButton("📚 כל הכתבות", callback_data="back_to_saved")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        return
    
    # בדיקה שזה קישור
    if not re.match(r'https?://', text):
        await update.message.reply_text(
            "לא הבנתי... 🤔\n\n"
            "אני יכול לעזור לך עם:\n"
            "• שליחת קישור לכתבה לשמירה\n"
            "• שימוש בכפתורים למטה\n"
            "• כתיבת `/help` לעזרה מלאה"
        )
        return
    
    # זה קישור - נעבד אותו
    await handle_url(text, update, context)

async def handle_url(url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בקישורים"""
    user_id = update.effective_user.id
    
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
    
    # שליחת הודעה נוספת עם המקלדת הקבועה
    await update.message.reply_text(
        "💡 **מה תרצה לעשות עכשיו?**\n\nהשתמש בכפתורים למטה:",
        reply_markup=get_main_keyboard()
    )

async def saved_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """הצגת כתבות שמורות"""
    user_id = update.effective_user.id
    articles = bot.get_user_articles(user_id)
    
    if not articles:
        await update.message.reply_text(
            "אין לך כתבות שמורות עדיין. שלח לי קישור כדי להתחיל! 📚", 
            reply_markup=get_main_keyboard()
        )
        return
    
    # הצגת כתבות עם כפתורים
    response = f"📚 **הכתבות השמורות שלך** ({len(articles)} כתבות)\n\n"
    response += "לחץ על כתבה לצפייה מלאה:"
    
    # יצירת כפתורים לכתבות
    keyboard = []
    
    # הצגת עד 10 כתבות ראשונות
    for article in articles[:10]:
        date_only = article.date_saved.split(' ')[0]
        button_text = f"{article.title[:40]}{'...' if len(article.title) > 40 else ''}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_article_{article.id}")])
    
    # אם יש יותר מ-10 כתבות
    if len(articles) > 10:
        keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(articles) - 10} כתבות", callback_data="show_more_articles")])
    
    # כפתורי פעולות נוספות
    keyboard.append([
        InlineKeyboardButton("🔍 חיפוש", callback_data="search"),
        InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
    ])
    keyboard.append([
        InlineKeyboardButton("💾 גיבוי", callback_data="backup")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בלחיצות על כפתורים"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data.startswith("view_article_"):
        article_id = int(data.split("_")[2])
        
        # טעינת פרטי הכתבה מהמסד נתונים
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # המרה לאובייקט SavedArticle
            # row מהמסד: (id, user_id, url, title, summary, full_text, category, tags, keywords, date_saved)
            # SavedArticle מצפה ל: (id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id)
            article = SavedArticle(
                id=row[0], url=row[2], title=row[3], summary=row[4], 
                full_text=row[5], category=row[6], tags=row[7], 
                keywords=row[8], date_saved=row[9], user_id=row[1]
            )
            
            # הכנת הכפתורים
            keyboard = [
                [
                    InlineKeyboardButton("📂 שנה קטגוריה", callback_data=f"change_category_{article_id}"),
                    InlineKeyboardButton("🔍 הצג מלא", callback_data=f"show_full_{article_id}")
                ],
                [
                    InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}"),
                    InlineKeyboardButton("↩️ חזור לרשימה", callback_data="back_to_saved")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # הצגת המידע על הכתבה
            response_text = f"""
📰 **{article.title}**

📂 **קטגוריה**: {article.category}
📅 **נשמר**: {article.date_saved.split(' ')[0]}
📝 **סיכום**:
{article.summary}

🔗 **קישור**: {article.url}
"""
            
            await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ לא נמצאה כתבה זו")
            
    elif data.startswith("view_article_list_"):
        article_id = int(data.split("_")[3])
        
        # טעינת פרטי הכתבה מהמסד נתונים
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # המרה לאובייקט SavedArticle
            # row מהמסד: (id, user_id, url, title, summary, full_text, category, tags, keywords, date_saved)
            # SavedArticle מצפה ל: (id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id)
            article = SavedArticle(
                id=row[0], url=row[2], title=row[3], summary=row[4], 
                full_text=row[5], category=row[6], tags=row[7], 
                keywords=row[8], date_saved=row[9], user_id=row[1]
            )
            
            # הכנת הכפתורים
            keyboard = [
                [
                    InlineKeyboardButton("📂 שנה קטגוריה", callback_data=f"change_category_{article_id}"),
                    InlineKeyboardButton("🔍 הצג מלא", callback_data=f"show_full_{article_id}")
                ],
                [
                    InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}"),
                    InlineKeyboardButton("↩️ חזור לרשימה", callback_data="back_to_list")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # הצגת המידע על הכתבה
            response_text = f"""
📰 **{article.title}**

📂 **קטגוריה**: {article.category}
📅 **נשמר**: {article.date_saved.split(' ')[0]}
📝 **סיכום**:
{article.summary}

🔗 **קישור**: {article.url}
"""
            
            await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ לא נמצאה כתבה זו")
    
    elif data.startswith("show_full_"):
        article_id = int(data.split("_")[2])
        
        # טעינת פרטי הכתבה מהמסד נתונים
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # המרה לאובייקט SavedArticle
            # row מהמסד: (id, user_id, url, title, summary, full_text, category, tags, keywords, date_saved)
            # SavedArticle מצפה ל: (id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id)
            article = SavedArticle(
                id=row[0], url=row[2], title=row[3], summary=row[4], 
                full_text=row[5], category=row[6], tags=row[7], 
                keywords=row[8], date_saved=row[9], user_id=row[1]
            )
            
            # חיתוך הטקסט המלא למניעת חריגה ממגבלת טלגרם (4096 תווים)
            max_length = 3200  # נשאיר מקום לכותרת ולכפתורים
            full_text = article.full_text
            
            # עיצוב נקי של הטקסט
            full_text = full_text.strip()
            
            if len(full_text) > max_length:
                full_text = full_text[:max_length] + "\n\n💭 *[הטקסט חתוך - הכתבה ארוכה מדי לתצוגה מלאה]*"
            
            # הכנת כפתורים מעוצבים
            keyboard = [
                [InlineKeyboardButton("↩️ חזור לסיכום", callback_data=f"back_to_article_{article_id}"),
                 InlineKeyboardButton("🗑️ מחק כתבה", callback_data=f"delete_{article_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # חילוץ תאריך נקי ומידע נוסף
            date_only = article.date_saved.split(' ')[0]
            word_count = len(article.full_text.split())
            reading_time = max(1, word_count // 200)  # הנחה של 200 מילים לדקה
            
            # הצגת הטקסט המלא במבנה מעוצב
            response_text = f"""
📖 **תצוגת טקסט מלא**

{'═' * 30}

📰 **{article.title}**

📂 **קטגוריה**: **{article.category}**
📅 **נשמר**: **{date_only}**
⏱️ **זמן קריאה**: **~{reading_time} דקות**
🔗 **מקור**: [לחץ כאן]({article.url})

{'─' * 30}

📝 **תוכן הכתבה**:

{full_text}

{'═' * 30}
"""
            
            await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ לא נמצאה כתבה זו")
        
    elif data.startswith("delete_"):
        article_id = int(data.split("_")[1])
        
        # טעינת פרטי הכתבה לאישור
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT title FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            title = row[0]
            # הצגת הודעת אישור
            keyboard = [
                [
                    InlineKeyboardButton("✅ כן, מחק", callback_data=f"confirm_delete_{article_id}"),
                    InlineKeyboardButton("❌ ביטול", callback_data=f"back_to_article_{article_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            confirm_text = f"""
⚠️ **אישור מחיקה**

האם אתה בטוח שברצונך למחוק את הכתבה:

📰 **{title[:80]}{'...' if len(title) > 80 else ''}**

❗ פעולה זו אינה ניתנת לביטול
"""
            
            await query.edit_message_text(confirm_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ לא נמצאה כתבה זו")
            
    elif data.startswith("confirm_delete_"):
        article_id = int(data.split("_")[2])
        bot.delete_article(article_id, user_id)
        
        # חזרה לרשימה המעודכנת אחרי מחיקה
        articles = bot.get_user_articles(user_id)
        
        if not articles:
            await query.edit_message_text("🗑️ הכתבה נמחקה בהצלחה!\n\n📚 אין לך יותר כתבות שמורות.")
            return
        
        # הצגת הרשימה המעודכנת
        response = f"🗑️ **הכתבה נמחקה בהצלחה!**\n\n📋 **הכתבות שלך** ({len(articles)} כתבות)\n\nבחר כתבה לצפייה או מחיקה:"
        
        keyboard = []
        
        # הצגת עד 6 כתבות עם כפתורי צפייה ומחיקה
        displayed_articles = articles[:6]
        
        for article in displayed_articles:
            title = f"{article.title[:30]}{'...' if len(article.title) > 30 else ''}"
            keyboard.append([
                InlineKeyboardButton(title, callback_data=f"view_article_list_{article.id}"),
                InlineKeyboardButton(f"🗑️ {article.id}", callback_data=f"delete_{article.id}")
            ])
        
        # אם יש יותר מ-6 כתבות
        if len(articles) > 6:
            keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(articles) - 6} כתבות", callback_data="show_more_list")])
        
        # כפתורי ניווט
        keyboard.append([
            InlineKeyboardButton("📚 תצוגת קטגוריות", callback_data="show_categories"),
            InlineKeyboardButton("🔍 חיפוש", callback_data="search")
        ])
        keyboard.append([
            InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data == "cancel_delete":
        await query.edit_message_text("❌ המחיקה בוטלה")
        
    elif data == "back_to_saved":
        # חזרה לרשימת הכתבות השמורות (/saved)
        articles = bot.get_user_articles(user_id)
        
        response = f"📚 **הכתבות השמורות שלך** ({len(articles)} כתבות)\n\n"
        response += "לחץ על כתבה לצפייה מלאה:"
        
        # יצירת כפתורים לכתבות
        keyboard = []
        
        # הצגת עד 10 כתבות ראשונות
        for article in articles[:10]:
            button_text = f"{article.title[:40]}{'...' if len(article.title) > 40 else ''}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_article_{article.id}")])
        
        # אם יש יותר מ-10 כתבות
        if len(articles) > 10:
            keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(articles) - 10} כתבות", callback_data="show_more_articles")])
        
        # כפתורי פעולות נוספות
        keyboard.append([
            InlineKeyboardButton("🔍 חיפוש", callback_data="search"),
            InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
        ])
        keyboard.append([
            InlineKeyboardButton("💾 גיבוי", callback_data="backup")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data == "back_to_list":
        # חזרה לרשימת הכתבות (/list)
        articles = bot.get_user_articles(user_id)
        
        response = f"📋 **רשימת הכתבות שלך** ({len(articles)} כתבות)\n\n"
        response += "בחר כתבה לצפייה או מחיקה:"
        
        # יצירת כפתורים לכתבות עם צפייה ומחיקה לכל כתבה
        keyboard = []
        
        # הצגת עד 6 כתבות עם כפתורי צפייה ומחיקה
        displayed_articles = articles[:6]
        
        for article in displayed_articles:
            title = f"{article.title[:30]}{'...' if len(article.title) > 30 else ''}"
            keyboard.append([
                InlineKeyboardButton(title, callback_data=f"view_article_list_{article.id}"),
                InlineKeyboardButton(f"🗑️ {article.id}", callback_data=f"delete_{article.id}")
            ])
        
        # אם יש יותר מ-6 כתבות
        if len(articles) > 6:
            keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(articles) - 6} כתבות", callback_data="show_more_list")])
        
        # כפתורי ניווט
        keyboard.append([
            InlineKeyboardButton("📚 תצוגת קטגוריות", callback_data="show_categories"),
            InlineKeyboardButton("🔍 חיפוש", callback_data="search")
        ])
        keyboard.append([
            InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data == "show_more_articles":
        # הצגת כל הכתבות
        articles = bot.get_user_articles(user_id)
        
        response = f"📚 **כל הכתבות שלך** ({len(articles)} כתבות)\n\n"
        response += "לחץ על כתבה לצפייה מלאה:"
        
        keyboard = []
        
        # הצגת כל הכתבות
        for article in articles:
            button_text = f"{article.title[:40]}{'...' if len(article.title) > 40 else ''}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_article_{article.id}")])
        
        # כפתורי פעולות
        keyboard.append([
            InlineKeyboardButton("🔍 חיפוש", callback_data="search"),
            InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
        ])
        keyboard.append([
            InlineKeyboardButton("💾 גיבוי", callback_data="backup")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data == "show_categories":
        # הצגת כתבות לפי קטגוריות
        articles = bot.get_user_articles(user_id)
        
        # קיבוץ לפי קטגוריות
        categories = {}
        for article in articles:
            if article.category not in categories:
                categories[article.category] = []
            categories[article.category].append(article)
        
        response = f"📂 **הכתבות שלך לפי קטגוריות** ({len(articles)} כתבות)\n\n"
        
        for category, cat_articles in categories.items():
            response += f"📂 **{category}** ({len(cat_articles)} כתבות)\n"
            for article in cat_articles[:3]:  # הצג 3 ראשונות
                response += f"   • {article.title[:40]}{'...' if len(article.title) > 40 else ''}\n"
            if len(cat_articles) > 3:
                response += f"   ... ועוד {len(cat_articles) - 3} כתבות\n"
            response += "\n"
        
        keyboard = [
            [InlineKeyboardButton("↩️ חזור לרשימה", callback_data="back_to_list")],
            [InlineKeyboardButton("🔍 חיפוש", callback_data="search")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data == "show_more_list":
        # הצגת כל הכתבות ברשימה מורחבת  
        articles = bot.get_user_articles(user_id)
        
        response = f"📋 **כל הכתבות שלך** ({len(articles)} כתבות)\n\n"
        response += "בחר כתבה לצפייה או מחיקה:"
        
        keyboard = []
        
        # הצגת כל הכתבות
        for article in articles:
            title = f"{article.title[:30]}{'...' if len(article.title) > 30 else ''}"
            keyboard.append([
                InlineKeyboardButton(title, callback_data=f"view_article_list_{article.id}"),
                InlineKeyboardButton(f"🗑️ {article.id}", callback_data=f"delete_{article.id}")
            ])
        
        # כפתורי ניווט
        keyboard.append([
            InlineKeyboardButton("📚 תצוגת קטגוריות", callback_data="show_categories"),
            InlineKeyboardButton("🔍 חיפוש", callback_data="search")
        ])
        keyboard.append([
            InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(response, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data.startswith("change_category_"):
        article_id = int(data.split("_")[2])
        # הצגת אפשרויות קטגוריות
        categories = ['טכנולוגיה', 'בריאות', 'כלכלה', 'פוליטיקה', 'השראה', 'כללי']
        
        keyboard = []
        for i in range(0, len(categories), 2):  # שתי קטגוריות בכל שורה
            row = []
            row.append(InlineKeyboardButton(categories[i], callback_data=f"set_cat_{article_id}_{categories[i]}"))
            if i + 1 < len(categories):
                row.append(InlineKeyboardButton(categories[i + 1], callback_data=f"set_cat_{article_id}_{categories[i + 1]}"))
            keyboard.append(row)
        
        # כפתור חזרה
        keyboard.append([InlineKeyboardButton("↩️ חזור", callback_data=f"back_to_article_{article_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("📂 **בחר קטגוריה חדשה:**", reply_markup=reply_markup, parse_mode='Markdown')
        
    elif data.startswith("set_cat_"):
        # עדכון הקטגוריה
        parts = data.split("_", 3)  # ["set", "cat", article_id, category]
        article_id = int(parts[2])
        new_category = parts[3]
        
        bot.update_article_category(article_id, new_category)
        
        # טעינת פרטי הכתבה מהמסד נתונים עם הקטגוריה המעודכנת
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # המרה לאובייקט SavedArticle
            # row מהמסד: (id, user_id, url, title, summary, full_text, category, tags, keywords, date_saved)
            # SavedArticle מצפה ל: (id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id)
            article = SavedArticle(
                id=row[0], url=row[2], title=row[3], summary=row[4], 
                full_text=row[5], category=row[6], tags=row[7], 
                keywords=row[8], date_saved=row[9], user_id=row[1]
            )
            
            # הכנת הכפתורים המקוריים
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
            
            # הצגת המידע המעודכן על הכתבה
            response_text = f"""
✅ **הקטגוריה עודכנה בהצלחה!**

📰 **כותרת**: {article.title}
📂 **קטגוריה**: {article.category}
📝 **סיכום**:
{article.summary}

🔗 **קישור**: {article.url}
"""
            
            await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ לא נמצאה כתבה זו")
        
    elif data.startswith("back_to_article_"):
        article_id = int(data.split("_")[-1])  # לקח את האלמנט האחרון
        
        # טעינת פרטי הכתבה מהמסד נתונים
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # המרה לאובייקט SavedArticle - התאמת סדר השדות
            # row מהמסד: (id, user_id, url, title, summary, full_text, category, tags, keywords, date_saved)
            # SavedArticle מצפה ל: (id, url, title, summary, full_text, category, tags, keywords, date_saved, user_id)
            article = SavedArticle(
                id=row[0], url=row[2], title=row[3], summary=row[4], 
                full_text=row[5], category=row[6], tags=row[7], 
                keywords=row[8], date_saved=row[9], user_id=row[1]
            )
            
            # הכנת הכפתורים המקוריים
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
            
            # הצגת המידע המקורי על הכתבה
            response_text = f"""
✅ **הכתבה השמורה שלך:**

📰 **כותרת**: {article.title}
📂 **קטגוריה**: {article.category}
📝 **סיכום**:
{article.summary}

🔗 **קישור**: {article.url}
"""
            
            await query.edit_message_text(response_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ לא נמצאה כתבה זו")
        
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
        
    elif data == "search":
        # התחלת חיפוש
        search_message = """
🔍 **חיפוש כתבות**

אני יכול לחפש בכתבות שלך לפי:
• כותרות הכתבות
• תוכן הסיכומים
• מילות מפתח אוטומטיות
• תגיות שהוספת

📝 **איך להשתמש:**
כתוב `/search [מילות חיפוש]`

**דוגמאות:**
• `/search טכנולוגיה AI`
• `/search בריאות תזונה`
• `/search ממשלה פוליטיקה`

💡 **טיפ**: אפשר לחפש כמה מילים יחד - המערכת תמצא כתבות שמכילות את כל המילים.
"""
        await query.edit_message_text(search_message, parse_mode='Markdown')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת חיפוש"""
    user_id = update.effective_user.id
    
    if not context.args:
        help_text = """
🔍 **חיפוש כתבות**

אני יכול לחפש בכתבות שלך לפי:
• כותרות הכתבות
• תוכן הסיכומים  
• מילות מפתח אוטומטיות
• תגיות שהוספת

📝 **שימוש:**
`/search [מילות חיפוש]`

**דוגמאות:**
• `/search טכנולוגיה AI`
• `/search בריאות תזונה`
• `/search ממשלה פוליטיקה`

💡 **טיפ**: אפשר לחפש כמה מילים יחד - המערכת תמצא כתבות שמכילות את כל המילים.
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    # איחוד מילות החיפוש
    search_query = ' '.join(context.args)
    
    # חיפוש כתבות
    found_articles = bot.search_articles(user_id, search_query)
    
    if not found_articles:
        await update.message.reply_text(f"🔍 לא נמצאו כתבות עבור: **{search_query}**\n\n💡 נסה מילים אחרות או בדוק איות", parse_mode='Markdown')
        return
    
    # הצגת תוצאות החיפוש
    response = f"🔍 **תוצאות חיפוש עבור: \"{search_query}\"**\n\n"
    response += f"נמצאו {len(found_articles)} כתבות:\n\n"
    
    # יצירת כפתורים לכתבות שנמצאו
    keyboard = []
    
    # הצגת עד 8 כתבות ראשונות
    for article in found_articles[:8]:
        date_only = article.date_saved.split(' ')[0]
        button_text = f"{article.title[:35]}{'...' if len(article.title) > 35 else ''}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_article_{article.id}")])
    
    # אם יש יותר מ-8 כתבות
    if len(found_articles) > 8:
        keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(found_articles) - 8} תוצאות", callback_data=f"search_more_{search_query}")])
    
    # כפתורי ניווט
    keyboard.append([
        InlineKeyboardButton("🔍 חיפוש חדש", callback_data="search"),
        InlineKeyboardButton("📚 כל הכתבות", callback_data="back_to_saved")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

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

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת מחיקה מהירה"""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text("שימוש: /delete [מספר_כתבה]\n\nכדי לראות את מספרי הכתבות, השתמש ב-/list")
        return
    
    try:
        article_id = int(context.args[0])
        
        # בדיקה שהכתבה קיימת
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT title FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            title = row[0]
            # הצגת הודעת אישור
            keyboard = [
                [
                    InlineKeyboardButton("✅ כן, מחק", callback_data=f"confirm_delete_{article_id}"),
                    InlineKeyboardButton("❌ ביטול", callback_data="cancel_delete")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            confirm_text = f"""
⚠️ **אישור מחיקה**

האם אתה בטוח שברצונך למחוק את הכתבה:

📰 **{title[:80]}{'...' if len(title) > 80 else ''}**

❗ פעולה זו אינה ניתנת לביטול
"""
            
            await update.message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ לא נמצאה כתבה עם המספר הזה")
            
    except ValueError:
        await update.message.reply_text("❌ מספר הכתבה חייב להיות מספר")
    except Exception as e:
        await update.message.reply_text(f"❌ שגיאה: {str(e)}")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """רשימת כתבות אינטראקטיבית"""
    user_id = update.effective_user.id
    articles = bot.get_user_articles(user_id)
    
    if not articles:
        await update.message.reply_text(
            "אין לך כתבות שמורות עדיין. שלח לי קישור כדי להתחיל! 📚", 
            reply_markup=get_main_keyboard()
        )
        return
    
    response = f"📋 **רשימת הכתבות שלך** ({len(articles)} כתבות)\n\n"
    response += "בחר כתבה לצפייה או מחיקה:"
    
    # יצירת כפתורים לכתבות עם צפייה ומחיקה לכל כתבה
    keyboard = []
    
    # הצגת עד 6 כתבות עם כפתורי צפייה ומחיקה
    displayed_articles = articles[:6]
    
    for article in displayed_articles:
        title = f"{article.title[:30]}{'...' if len(article.title) > 30 else ''}"
        keyboard.append([
            InlineKeyboardButton(title, callback_data=f"view_article_list_{article.id}"),
            InlineKeyboardButton(f"🗑️ {article.id}", callback_data=f"delete_{article.id}")
        ])
    
    # אם יש יותר מ-6 כתבות
    if len(articles) > 6:
        keyboard.append([InlineKeyboardButton(f"📋 הצג עוד {len(articles) - 6} כתבות", callback_data="show_more_list")])
    
    # כפתורי ניווט
    keyboard.append([
        InlineKeyboardButton("📚 תצוגת קטגוריות", callback_data="show_categories"),
        InlineKeyboardButton("🔍 חיפוש", callback_data="search")
    ])
    keyboard.append([
        InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')

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
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("tag", tag_command))
    
    # טיפול בהודעות טקסט - כפתורים, חיפוש וקישורים
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # טיפול בכפתורים
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 הבוט מופעל במצב polling...")
    print("📱 פקודת /saved אמורה לעבוד עכשיו!")
    
    # הפעלת הבוט עם Polling (לפיתוח מקומי)
    application.run_polling()

# Flask routes הוסרו - הבוט עובד במצב polling

if __name__ == '__main__':
    main()
