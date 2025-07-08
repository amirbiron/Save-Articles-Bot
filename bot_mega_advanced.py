#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 MEGA ADVANCED TELEGRAM READ LATER BOT 🚀
הבוט המתקדם ביותר לשמירת מאמרים!

Features:
✅ Smart content extraction with newspaper3k + fallback
✅ AI-powered categorization (7 categories)
✅ Intelligent text summarization
✅ User statistics and analytics
✅ Search functionality
✅ Favorites and reading tracking
✅ Multi-language support
✅ Performance monitoring
✅ Advanced database with indexes
✅ Caching for better performance
"""

import logging
import sqlite3
import json
import re
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
from dataclasses import dataclass
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Optional advanced content extraction
try:
    from newspaper import Article
    NEWSPAPER_AVAILABLE = True
    print("📰 Newspaper3k זמין - חילוץ מתקדם!")
except ImportError:
    NEWSPAPER_AVAILABLE = False
    print("📝 Newspaper3k לא זמין - חילוץ בסיסי")

# Load environment
load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "mega_advanced_bot.db"

if not TELEGRAM_TOKEN:
    print("❌ שגיאה: TELEGRAM_TOKEN לא הוגדר ב-.env")
    exit(1)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('mega_bot.log')
    ]
)
logger = logging.getLogger(__name__)

print("🚀 מתחיל אתחול הבוט המתקדם...")

class MegaAdvancedBot:
    """הבוט המתקדם ביותר לשמירת מאמרים"""
    
    def __init__(self):
        print("🔧 מאתחל רכיבי בוט...")
        
        # Initialize components
        self.init_database()
        self.init_content_extractor()
        self.init_categorizer()
        self.init_summarizer()
        self.init_cache()
        self.init_performance_monitor()
        
        print("✅ הבוט המתקדם מוכן!")
    
    def init_database(self):
        """Initialize advanced database"""
        print("🗄️ מאתחל מסד נתונים מתקדם...")
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Advanced articles table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'כללי',
                language TEXT DEFAULT 'he',
                reading_time INTEGER DEFAULT 1,
                extraction_method TEXT DEFAULT 'unknown',
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_read TIMESTAMP,
                is_favorite BOOLEAN DEFAULT 0,
                view_count INTEGER DEFAULT 0
            )
        ''')
        
        # User statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                articles_saved INTEGER DEFAULT 0,
                articles_read INTEGER DEFAULT 0,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Performance indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_articles ON articles(user_id, date_saved)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON articles(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_language ON articles(language)')
        
        conn.commit()
        conn.close()
        print("✅ מסד נתונים מוכן!")
    
    def init_content_extractor(self):
        """Initialize smart content extraction"""
        print("📰 מאתחל מחלץ תוכן חכם...")
        
        self.extraction_methods = ['newspaper3k', 'beautifulsoup', 'fallback']
        
        # Smart selectors for different content types
        self.title_selectors = [
            'h1.entry-title', 'h1.post-title', 'h1.article-title',
            '.story-headline', '.headline', '.title', 'h1', 'title'
        ]
        
        self.content_selectors = [
            'article', '.entry-content', '.post-content', '.article-content',
            '.story-body', '.content', '.article-body', 'main .text',
            '.post-body', '[itemprop="articleBody"]'
        ]
        
        # Language detection patterns
        self.hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
        self.arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        
        print("✅ מחלץ תוכן מוכן!")
    
    def init_categorizer(self):
        """Initialize AI categorizer"""
        print("🤖 מאתחל מסווג קטגוריות חכם...")
        
        self.categories = {
            'טכנולוגיה': [
                'טכנולוגיה', 'אפליקציה', 'סמארטפון', 'מחשב', 'אינטרנט', 'סייבר', 
                'AI', 'בינה מלאכותית', 'blockchain', 'crypto', 'פיתוח', 'תוכנה',
                'גוגל', 'אפל', 'מיקרוסופט', 'פייסבוק', 'אמזון', 'נטפליקס', 'פייסבוק'
            ],
            'בריאות': [
                'בריאות', 'רפואה', 'מחקר', 'טיפול', 'תזונה', 'ספורט', 'כושר',
                'פסיכולוגיה', 'נפש', 'דיאטה', 'ויטמין', 'חיסון', 'קורונה',
                'רופא', 'בית חולים', 'תרופה', 'מחלה'
            ],
            'כלכלה': [
                'כלכלה', 'כספים', 'השקעות', 'בורסה', 'עסקים', 'חברה', 'סטארטאפ',
                'מניות', 'ביטקוין', 'בנק', 'אינפלציה', 'משכורת', 'מס',
                'נדלן', 'הלוואה', 'חוב', 'ביטוח'
            ],
            'פוליטיקה': [
                'פוליטיקה', 'ממשלה', 'כנסת', 'בחירות', 'מדינה', 'חוק', 'מדיניות',
                'שר', 'ראש ממשלה', 'נשיא', 'מפלגה', 'קואליציה', 'אופוזיציה'
            ],
            'ספורט': [
                'ספורט', 'כדורגל', 'כדורסל', 'טניס', 'שחייה', 'ריצה', 'אימון',
                'אולימפיאדה', 'מונדיאל', 'ליגה', 'קבוצה', 'שחקן', 'מאמן'
            ],
            'תרבות': [
                'תרבות', 'מוזיקה', 'קולנוע', 'ספר', 'אמנות', 'תיאטרון', 'מוזיאון',
                'פסטיבל', 'זמר', 'שחקן', 'במאי', 'סופר', 'ציור'
            ],
            'השראה': [
                'השראה', 'מוטיבציה', 'אישיות', 'הצלחה', 'חלומות', 'מטרות',
                'פיתוח אישי', 'מנהיגות', 'יזמות', 'כישורים', 'למידה'
            ]
        }
        
        print("✅ מסווג קטגוריות מוכן!")
    
    def init_summarizer(self):
        """Initialize smart text summarizer"""
        print("📝 מאתחל מסכם טקסט חכם...")
        
        self.hebrew_stopwords = {
            'של', 'את', 'על', 'אל', 'עם', 'כל', 'כי', 'אם', 'לא', 'או', 'גם', 'רק',
            'אבל', 'אך', 'כך', 'כן', 'לכן', 'אז', 'שם', 'פה', 'זה', 'זו', 'הוא', 'היא',
            'אני', 'אתה', 'אנחנו', 'אתם', 'הם', 'הן', 'יש', 'יהיה', 'היה', 'להיות'
        }
        
        print("✅ מסכם טקסט מוכן!")
    
    def init_cache(self):
        """Initialize cache system"""
        print("🧠 מאתחל מערכת מטמון...")
        
        self.url_cache = {}  # Simple cache for URLs
        self.cache_max_size = 100
        self.cache_expiry = 3600  # 1 hour
        
        print("✅ מטמון מוכן!")
    
    def init_performance_monitor(self):
        """Initialize performance monitoring"""
        print("📊 מאתחל מוניטור ביצועים...")
        
        self.performance_stats = {
            'articles_processed': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'total_processing_time': 0,
            'start_time': time.time()
        }
        
        print("✅ מוניטור ביצועים מוכן!")
    
    def extract_content(self, url: str) -> Optional[Dict]:
        """Advanced content extraction with multiple fallbacks"""
        start_time = time.time()
        
        print(f"🔄 מעבד: {url}")
        
        # Check cache
        url_hash = hashlib.md5(url.encode()).hexdigest()
        if url_hash in self.url_cache:
            cache_data = self.url_cache[url_hash]
            if time.time() - cache_data['timestamp'] < self.cache_expiry:
                self.performance_stats['cache_hits'] += 1
                print("💾 נמצא במטמון")
                return cache_data['data']
        
        self.performance_stats['cache_misses'] += 1
        
        # Try different extraction methods
        result = None
        
        # Method 1: newspaper3k (if available)
        if NEWSPAPER_AVAILABLE and not result:
            result = self._extract_with_newspaper(url)
        
        # Method 2: BeautifulSoup
        if not result:
            result = self._extract_with_bs4(url)
        
        # Process result
        if result:
            result['reading_time'] = self._estimate_reading_time(result['content'])
            result['language'] = self._detect_language(result['title'] + ' ' + result['content'][:500])
            
            # Cache result
            if len(self.url_cache) >= self.cache_max_size:
                # Remove oldest entry
                oldest_key = min(self.url_cache.keys(), 
                               key=lambda k: self.url_cache[k]['timestamp'])
                del self.url_cache[oldest_key]
            
            self.url_cache[url_hash] = {
                'data': result,
                'timestamp': time.time()
            }
            
            self.performance_stats['successful_extractions'] += 1
            print(f"✅ חולץ בהצלחה: {result['title'][:50]}...")
        else:
            self.performance_stats['failed_extractions'] += 1
            print("❌ חילוץ נכשל")
        
        self.performance_stats['articles_processed'] += 1
        self.performance_stats['total_processing_time'] += time.time() - start_time
        
        return result
    
    def _extract_with_newspaper(self, url: str) -> Optional[Dict]:
        """Extract using newspaper3k"""
        try:
            article = Article(url, language='he')
            article.config.browser_user_agent = 'Mozilla/5.0 (compatible; MegaBot/1.0)'
            article.config.request_timeout = 15
            
            article.download()
            article.parse()
            
            if article.text and len(article.text.strip()) > 100:
                return {
                    'title': article.title or 'כותרת לא זמינה',
                    'content': article.text.strip()[:8000],  # Limit content size
                    'method': 'newspaper3k'
                }
        except Exception as e:
            logger.warning(f"Newspaper extraction failed: {e}")
        
        return None
    
    def _extract_with_bs4(self, url: str) -> Optional[Dict]:
        """Extract using BeautifulSoup with smart selectors"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'he,en-US;q=0.7,en;q=0.3'
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
                tag.decompose()
            
            # Extract title
            title = self._extract_title(soup)
            
            # Extract content
            content = self._extract_content_text(soup)
            
            if title and content and len(content) > 100:
                return {
                    'title': title,
                    'content': content[:8000],  # Limit content size
                    'method': 'beautifulsoup'
                }
                
        except Exception as e:
            logger.warning(f"BeautifulSoup extraction failed: {e}")
        
        return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract title using smart selectors"""
        for selector in self.title_selectors:
            try:
                element = soup.select_one(selector)
                if element and element.get_text().strip():
                    title = element.get_text().strip()
                    title = re.sub(r'\s+', ' ', title)
                    return title[:200]
            except:
                continue
        
        return "כותרת לא זמינה"
    
    def _extract_content_text(self, soup: BeautifulSoup) -> str:
        """Extract main content using smart selectors"""
        for selector in self.content_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text().strip()
                    if len(text) > 200:
                        return re.sub(r'\s+', ' ', text)
            except:
                continue
        
        # Fallback: extract all paragraphs
        try:
            paragraphs = soup.find_all('p')
            text = ' '.join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
            return text if len(text) > 200 else ""
        except:
            return ""
    
    def _detect_language(self, text: str) -> str:
        """Detect text language"""
        if self.hebrew_pattern.search(text):
            return 'עברית'
        elif self.arabic_pattern.search(text):
            return 'ערבית'
        return 'אנגלית'
    
    def _estimate_reading_time(self, text: str) -> int:
        """Estimate reading time in minutes"""
        words = len(text.split())
        return max(1, round(words / 200))  # 200 words per minute
    
    def categorize_article(self, title: str, content: str) -> str:
        """AI-powered article categorization"""
        text = f"{title} {content[:1000]}".lower()  # Use title + first 1000 chars
        
        category_scores = {}
        
        for category, keywords in self.categories.items():
            score = 0
            
            # Count keyword matches with different weights
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # Title matches get higher weight
                if keyword_lower in title.lower():
                    score += 3
                
                # Content matches
                score += text.count(keyword_lower)
            
            if score > 0:
                category_scores[category] = score
        
        if category_scores:
            return max(category_scores, key=category_scores.get)
        
        return 'כללי'
    
    def smart_summarize(self, text: str, max_length: int = 300) -> str:
        """Create intelligent summary"""
        try:
            # Split into sentences
            sentences = re.split(r'[.!?]+\s+', text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 15]
            
            if len(sentences) <= 2:
                return '. '.join(sentences)
            
            # Score sentences by importance
            scored_sentences = []
            
            # Calculate word frequencies
            words = re.findall(r'\b\w+\b', text.lower())
            word_freq = {}
            for word in words:
                if word not in self.hebrew_stopwords and len(word) > 2:
                    word_freq[word] = word_freq.get(word, 0) + 1
            
            for i, sentence in enumerate(sentences):
                score = 0
                sentence_words = re.findall(r'\b\w+\b', sentence.lower())
                
                # Frequency-based scoring
                for word in sentence_words:
                    if word in word_freq:
                        score += word_freq[word]
                
                # Position bonus (first sentences are often important)
                if i < len(sentences) * 0.3:
                    score *= 1.5
                
                # Length bonus for medium-length sentences
                if 20 < len(sentence) < 150:
                    score *= 1.2
                
                scored_sentences.append((sentence, score, i))
            
            # Sort by score and select top sentences
            scored_sentences.sort(key=lambda x: x[1], reverse=True)
            
            # Select sentences that fit within max_length
            selected = []
            total_length = 0
            
            for sentence_data in scored_sentences:
                sentence, score, position = sentence_data
                if total_length + len(sentence) <= max_length - 50:  # Leave buffer
                    selected.append(sentence_data)
                    total_length += len(sentence)
                    
                    if len(selected) >= 3:  # Max 3 sentences
                        break
            
            if not selected:
                selected = [scored_sentences[0]] if scored_sentences else []
            
            # Sort by original position and join
            selected.sort(key=lambda x: x[2])
            summary = '. '.join([s[0] for s in selected])
            
            return summary if len(summary) <= max_length else summary[:max_length] + "..."
            
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            # Fallback to simple truncation
            sentences = text.split('.')[:2]
            return '. '.join(sentences).strip() + "."
    
    def save_article(self, user_id: int, url: str, title: str, summary: str, 
                    content: str, category: str, language: str, reading_time: int, 
                    extraction_method: str) -> int:
        """Save article to database"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO articles (user_id, url, title, summary, content, category, 
                                language, reading_time, extraction_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, url, title, summary, content, category, language, reading_time, extraction_method))
        
        article_id = cursor.lastrowid
        
        # Update user stats
        cursor.execute('''
            INSERT OR REPLACE INTO user_stats (user_id, articles_saved, last_activity)
            VALUES (?, COALESCE((SELECT articles_saved FROM user_stats WHERE user_id = ?), 0) + 1, ?)
        ''', (user_id, user_id, datetime.now()))
        
        conn.commit()
        conn.close()
        
        print(f"💾 מאמר נשמר: ID {article_id}")
        return article_id