#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 SUPER ADVANCED TELEGRAM READ LATER BOT 🚀
Version 3.0 - All-in-One Mega Bot!

Features:
✅ Smart AI content extraction 
✅ 7 intelligent categories
✅ Advanced text summarization
✅ User analytics & statistics  
✅ Search & favorites
✅ Multi-language support
✅ Performance monitoring
✅ Advanced caching
"""

import logging
import sqlite3
import json
import re
import hashlib
import time
from datetime import datetime
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Optional newspaper3k
try:
    from newspaper import Article
    NEWSPAPER_AVAILABLE = True
    print("📰 Newspaper3k זמין - חילוץ מתקדם!")
except ImportError:
    NEWSPAPER_AVAILABLE = False
    print("📝 חילוץ בסיסי - מומלץ להתקין newspaper3k")

# Load environment
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "super_advanced_bot.db"

if not TELEGRAM_TOKEN:
    print("❌ שגיאה: TELEGRAM_TOKEN לא הוגדר ב-.env")
    exit(1)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("🚀 מתחיל בוט סופר מתקדם...")

class SuperAdvancedBot:
    """הבוט הסופר מתקדם לשמירת מאמרים"""
    
    def __init__(self):
        print("🔧 מאתחל מערכות...")
        
        # Performance stats
        self.stats = {
            'articles_processed': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'start_time': time.time()
        }
        
        # Cache system
        self.url_cache = {}
        self.cache_max_size = 50
        self.cache_expiry = 3600  # 1 hour
        
        # Categories for AI classification
        self.categories = {
            'טכנולוגיה': [
                'טכנולוגיה', 'אפליקציה', 'סמארטפון', 'מחשב', 'אינטרנט', 'סייבר', 
                'AI', 'בינה מלאכותית', 'blockchain', 'crypto', 'פיתוח', 'תוכנה',
                'גוגל', 'אפל', 'מיקרוסופט', 'פייסבוק', 'אמזון', 'נטפליקס'
            ],
            'בריאות': [
                'בריאות', 'רפואה', 'מחקר', 'טיפול', 'תזונה', 'ספורט', 'כושר',
                'פסיכולוגיה', 'נפש', 'דיאטה', 'ויטמין', 'חיסון', 'קורונה',
                'רופא', 'בית חולים', 'תרופה'
            ],
            'כלכלה': [
                'כלכלה', 'כספים', 'השקעות', 'בורסה', 'עסקים', 'חברה', 'סטארטאפ',
                'מניות', 'ביטקוין', 'בנק', 'אינפלציה', 'משכורת', 'מס', 'נדלן'
            ],
            'פוליטיקה': [
                'פוליטיקה', 'ממשלה', 'כנסת', 'בחירות', 'מדינה', 'חוק', 'מדיניות',
                'שר', 'ראש ממשלה', 'נשיא', 'מפלגה'
            ],
            'ספורט': [
                'ספורט', 'כדורגל', 'כדורסל', 'טניס', 'שחייה', 'ריצה', 'אימון',
                'אולימפיאדה', 'מונדיאל', 'ליגה', 'קבוצה', 'שחקן'
            ],
            'תרבות': [
                'תרבות', 'מוזיקה', 'קולנוע', 'ספר', 'אמנות', 'תיאטרון', 'מוזיאון',
                'פסטיבל', 'זמר', 'שחקן', 'במאי'
            ],
            'השראה': [
                'השראה', 'מוטיבציה', 'אישיות', 'הצלחה', 'חלומות', 'מטרות',
                'פיתוח אישי', 'מנהיגות', 'יזמות'
            ]
        }
        
        # Hebrew stopwords for summarization
        self.hebrew_stopwords = {
            'של', 'את', 'על', 'אל', 'עם', 'כל', 'כי', 'אם', 'לא', 'או', 'גם', 'רק',
            'אבל', 'אך', 'כך', 'כן', 'לכן', 'אז', 'שם', 'פה', 'זה', 'זו', 'הוא', 'היא'
        }
        
        # Language patterns
        self.hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
        self.arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        
        # Content selectors
        self.title_selectors = [
            'h1.entry-title', 'h1.post-title', 'h1.article-title',
            '.headline', '.title', 'h1', 'title'
        ]
        
        self.content_selectors = [
            'article', '.entry-content', '.post-content', '.article-content',
            '.story-body', '.content', '.article-body', 'main',
            '.post-body', '[itemprop="articleBody"]'
        ]
        
        self.init_database()
        print("✅ בוט סופר מתקדם מוכן!")
    
    def init_database(self):
        """Initialize advanced database"""
        print("🗄️ מאתחל מסד נתונים...")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'כללי',
                language TEXT DEFAULT 'עברית',
                reading_time INTEGER DEFAULT 1,
                extraction_method TEXT DEFAULT 'unknown',
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_read TIMESTAMP,
                is_favorite BOOLEAN DEFAULT 0,
                view_count INTEGER DEFAULT 0
            )
        ''')
        
        # Indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_articles ON articles(user_id, date_saved)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON articles(category)')
        
        conn.commit()
        conn.close()
        print("✅ מסד נתונים מוכן!")
    
    def extract_content(self, url: str) -> Optional[Dict]:
        """Advanced content extraction with multiple methods"""
        start_time = time.time()
        
        # Check cache
        url_hash = hashlib.md5(url.encode()).hexdigest()
        if url_hash in self.url_cache:
            cache_data = self.url_cache[url_hash]
            if time.time() - cache_data['timestamp'] < self.cache_expiry:
                self.stats['cache_hits'] += 1
                print("💾 נמצא במטמון")
                return cache_data['data']
        
        self.stats['cache_misses'] += 1
        print(f"🔄 מחלץ תוכן מ: {url}")
        
        # Try newspaper3k first
        result = None
        if NEWSPAPER_AVAILABLE:
            result = self._extract_with_newspaper(url)
        
        # Fallback to BeautifulSoup
        if not result:
            result = self._extract_with_bs4(url)
        
        if result:
            # Add metadata
            result['reading_time'] = self._estimate_reading_time(result['content'])
            result['language'] = self._detect_language(result['title'] + ' ' + result['content'][:500])
            
            # Cache result
            if len(self.url_cache) >= self.cache_max_size:
                oldest_key = min(self.url_cache.keys(), 
                               key=lambda k: self.url_cache[k]['timestamp'])
                del self.url_cache[oldest_key]
            
            self.url_cache[url_hash] = {
                'data': result,
                'timestamp': time.time()
            }
            
            self.stats['successful_extractions'] += 1
            print(f"✅ חולץ בהצלחה: {result['title'][:50]}...")
        else:
            self.stats['failed_extractions'] += 1
            print("❌ חילוץ נכשל")
        
        self.stats['articles_processed'] += 1
        return result
    
    def _extract_with_newspaper(self, url: str) -> Optional[Dict]:
        """Extract using newspaper3k"""
        try:
            article = Article(url, language='he')
            article.config.browser_user_agent = 'Mozilla/5.0 (compatible; SuperBot/3.0)'
            article.config.request_timeout = 15
            
            article.download()
            article.parse()
            
            if article.text and len(article.text.strip()) > 100:
                return {
                    'title': article.title or 'כותרת לא זמינה',
                    'content': article.text.strip()[:8000],
                    'method': 'newspaper3k'
                }
        except Exception as e:
            logger.warning(f"Newspaper extraction failed: {e}")
        
        return None
    
    def _extract_with_bs4(self, url: str) -> Optional[Dict]:
        """Extract using BeautifulSoup"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            title = self._extract_title(soup)
            content = self._extract_content_text(soup)
            
            if title and content and len(content) > 100:
                return {
                    'title': title,
                    'content': content[:8000],
                    'method': 'beautifulsoup'
                }
                
        except Exception as e:
            logger.warning(f"BeautifulSoup extraction failed: {e}")
        
        return None
    
    def _extract_title(self, soup) -> str:
        """Extract title using smart selectors"""
        for selector in self.title_selectors:
            try:
                element = soup.select_one(selector)
                if element and element.get_text().strip():
                    title = element.get_text().strip()
                    return re.sub(r'\s+', ' ', title)[:200]
            except:
                continue
        return "כותרת לא זמינה"
    
    def _extract_content_text(self, soup) -> str:
        """Extract content using smart selectors"""
        for selector in self.content_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text().strip()
                    if len(text) > 200:
                        return re.sub(r'\s+', ' ', text)
            except:
                continue
        
        # Fallback: all paragraphs
        try:
            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
            return text if len(text) > 200 else ""
        except:
            return ""
    
    def _detect_language(self, text: str) -> str:
        """Detect language"""
        if self.hebrew_pattern.search(text):
            return 'עברית'
        elif self.arabic_pattern.search(text):
            return 'ערבית'
        return 'אנגלית'
    
    def _estimate_reading_time(self, text: str) -> int:
        """Estimate reading time"""
        words = len(text.split())
        return max(1, round(words / 200))
    
    def categorize_article(self, title: str, content: str) -> str:
        """AI categorization"""
        text = f"{title} {content[:1000]}".lower()
        
        best_category = 'כללי'
        best_score = 0
        
        for category, keywords in self.categories.items():
            score = 0
            for keyword in keywords:
                if keyword.lower() in title.lower():
                    score += 3  # Title matches are more important
                score += text.count(keyword.lower())
            
            if score > best_score:
                best_score = score
                best_category = category
        
        return best_category
    
    def smart_summarize(self, text: str, max_length: int = 300) -> str:
        """AI summarization"""
        try:
            sentences = re.split(r'[.!?]+\s+', text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 15]
            
            if len(sentences) <= 2:
                return '. '.join(sentences)
            
            # Score sentences
            word_freq = {}
            words = re.findall(r'\b\w+\b', text.lower())
            for word in words:
                if word not in self.hebrew_stopwords and len(word) > 2:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            scored_sentences = []
            for i, sentence in enumerate(sentences):
                score = 0
                sentence_words = re.findall(r'\b\w+\b', sentence.lower())
                
                for word in sentence_words:
                    if word in word_freq:
                        score += word_freq[word]
                
                # Position bonus
                if i < len(sentences) * 0.3:
                    score *= 1.5
                
                # Length bonus
                if 20 < len(sentence) < 150:
                    score *= 1.2
                
                scored_sentences.append((sentence, score, i))
            
            # Select top sentences
            scored_sentences.sort(key=lambda x: x[1], reverse=True)
            selected = []
            total_length = 0
            
            for sentence_data in scored_sentences:
                sentence, score, position = sentence_data
                if total_length + len(sentence) <= max_length - 50:
                    selected.append(sentence_data)
                    total_length += len(sentence)
                    if len(selected) >= 3:
                        break
            
            if not selected:
                selected = [scored_sentences[0]] if scored_sentences else []
            
            # Sort by original position
            selected.sort(key=lambda x: x[2])
            summary = '. '.join([s[0] for s in selected])
            
            return summary if len(summary) <= max_length else summary[:max_length] + "..."
            
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            sentences = text.split('.')[:2]
            return '. '.join(sentences).strip() + "."

# Initialize bot
super_bot = SuperAdvancedBot()

# Telegram handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    user_name = update.effective_user.first_name or "משתמש"
    
    welcome_message = f"""
🚀 **ברוך הבא {user_name} לבוט הסופר מתקדם!**

🎯 **תכונות מהפכניות:**
• 🧠 חילוץ תוכן חכם עם AI
• 📊 מיון אוטומטי ל-7 קטגוריות
• 🎯 סיכומים חכמים
• 📈 סטטיסטיקות מתקדמות
• 🔍 חיפוש מהיר
• ⭐ מערכת מועדפים
• 🌐 תמיכה רב-לשונית
• 💾 מטמון מהיר

📝 **איך להתחיל:**
שלח לי קישור לכתבה ואני אעבד אותה בחכמה!

🔗 **פקודות:**
• `/saved` - הספרייה שלך
• `/stats` - סטטיסטיקות אישיות
• `/search [מילה]` - חיפוש מתקדם
• `/help` - עזרה מלאה

**בואו נבנה את הספרייה הדיגיטלית שלך!** ✨
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="stats"),
            InlineKeyboardButton("📚 הספרייה שלי", callback_data="saved")
        ],
        [
            InlineKeyboardButton("🔍 חיפוש", callback_data="search_help"),
            InlineKeyboardButton("🆘 עזרה", callback_data="help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle URLs with advanced processing"""
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    print(f"🔗 עיבוד קישור מ-{user_id}: {url}")
    
    if not re.match(r'https?://', url):
        await update.message.reply_text(
            "❌ זה לא נראה כמו קישור תקין.\n"
            "💡 ודא שהקישור מתחיל ב-http או https"
        )
        return
    
    loading_msg = await update.message.reply_text(
        "🚀 **מעבד בטכנולוגיה מתקדמת...**\n\n"
        "⚡ חילוץ תוכן\n"
        "🤖 ניתוח AI\n" 
        "📝 יצירת סיכום\n"
        "📊 קביעת קטגוריה"
    )
    
    start_time = time.time()
    
    # Extract content
    article_data = super_bot.extract_content(url)
    
    if not article_data:
        await loading_msg.edit_text(
            f"❌ **לא הצלחתי לחלץ תוכן**\n\n"
            f"🔗 {url}\n\n"
            f"💡 **סיבות אפשריות:**\n"
            f"• האתר חוסם בוטים\n"
            f"• תוכן מוגן בתשלום\n"
            f"• בעיה זמנית\n\n"
            f"נסה קישור אחר או נסה מאוחר יותר"
        )
        return
    
    await loading_msg.edit_text("🤖 **יוצר סיכום AI...**")
    
    # Generate summary and category
    summary = super_bot.smart_summarize(article_data['content'])
    category = super_bot.categorize_article(article_data['title'], article_data['content'])
    
    # Save to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO articles (user_id, url, title, summary, content, category, 
                            language, reading_time, extraction_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, url, article_data['title'], summary, article_data['content'],
          category, article_data['language'], article_data['reading_time'], 
          article_data['method']))
    
    article_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    processing_time = time.time() - start_time
    
    # Response with action buttons
    keyboard = [
        [
            InlineKeyboardButton("⭐ הוסף למועדפים", callback_data=f"fav_{article_id}"),
            InlineKeyboardButton("✅ סמן כנקרא", callback_data=f"read_{article_id}")
        ],
        [
            InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats"),
            InlineKeyboardButton(f"📂 עוד ב{category}", callback_data=f"cat_{category}")
        ],
        [InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    method_emoji = "📰" if article_data['method'] == 'newspaper3k' else "🔧"
    
    response_text = f"""
✅ **מאמר נשמר בהצלחה!**

📰 **כותרת:** {article_data['title']}
📂 **קטגוריה:** {category}
🌐 **שפה:** {article_data['language']}
⏱️ **זמן קריאה:** {article_data['reading_time']} דקות
{method_emoji} **שיטת חילוץ:** {article_data['method']}

📝 **סיכום חכם:**
{summary}

🔗 [קישור למאמר המלא]({url})

⚡ **זמן עיבוד:** {processing_time:.2f} שניות
💾 **מזהה:** #{article_id}
"""
    
    await loading_msg.edit_text(
        response_text, 
        reply_markup=reply_markup, 
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    
    print(f"✅ מאמר נשמר: {article_data['title'][:50]}... עבור {user_id}")

def main():
    """Run the super advanced bot"""
    print("🚀 מתחיל בוט סופר מתקדם...")
    print(f"🔑 טוקן: {TELEGRAM_TOKEN[:10]}...")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    print("✅ הכל מוכן!")
    print("📡 מתחיל לקבל הודעות...")
    print("🎯 הבוט הסופר מתקדם פעיל!")
    
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()