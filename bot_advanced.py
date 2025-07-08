#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Telegram Read Later Bot
Features:
- Smart content extraction with fallback
- Auto-categorization 
- User statistics
- Caching for performance
- Multiple language support
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
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from cachetools import TTLCache

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Optional advanced content extraction
try:
    from newspaper import Article
    NEWSPAPER_AVAILABLE = True
except ImportError:
    NEWSPAPER_AVAILABLE = False
    print("📰 newspaper3k לא מותקן - נשתמש במקסם פשוט")

# Load environment
load_dotenv()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('advanced_bot.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "read_later_advanced.db"

if not TELEGRAM_TOKEN:
    print("❌ שגיאה: TELEGRAM_TOKEN לא הוגדר ב-.env")
    exit(1)

@dataclass
class Article:
    """Article data structure"""
    id: int
    user_id: int
    url: str
    title: str
    summary: str
    content: str
    category: str
    language: str
    reading_time: int
    tags: str
    date_saved: str
    date_read: Optional[str] = None
    is_favorite: bool = False

class PerformanceMonitor:
    """Performance tracking"""
    def __init__(self):
        self.stats = {
            'articles_processed': 0,
            'successful_extractions': 0,
            'failed_extractions': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'average_processing_time': 0,
            'start_time': time.time()
        }
    
    def log_extraction(self, success: bool, duration: float):
        self.stats['articles_processed'] += 1
        if success:
            self.stats['successful_extractions'] += 1
        else:
            self.stats['failed_extractions'] += 1
        
        # Update average processing time
        total = self.stats['articles_processed']
        current_avg = self.stats['average_processing_time']
        self.stats['average_processing_time'] = (current_avg * (total - 1) + duration) / total
    
    def log_cache(self, hit: bool):
        if hit:
            self.stats['cache_hits'] += 1
        else:
            self.stats['cache_misses'] += 1
    
    def get_stats(self) -> Dict:
        uptime = time.time() - self.stats['start_time']
        cache_total = self.stats['cache_hits'] + self.stats['cache_misses']
        cache_rate = (self.stats['cache_hits'] / cache_total * 100) if cache_total > 0 else 0
        success_rate = (self.stats['successful_extractions'] / max(self.stats['articles_processed'], 1) * 100)
        
        return {
            'uptime_hours': uptime / 3600,
            'articles_processed': self.stats['articles_processed'],
            'success_rate': success_rate,
            'cache_hit_rate': cache_rate,
            'avg_processing_time': self.stats['average_processing_time'],
            'articles_per_hour': self.stats['articles_processed'] / max(uptime / 3600, 0.1)
        }

class SmartContentExtractor:
    """Advanced content extraction with multiple methods"""
    
    def __init__(self):
        self.cache = TTLCache(maxsize=500, ttl=3600)  # 1 hour cache
        self.monitor = PerformanceMonitor()
        
        # Language patterns
        self.hebrew_pattern = re.compile(r'[\u0590-\u05FF]')
        self.arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        
        # Smart selectors for different sites
        self.selectors = {
            'title': [
                'h1.entry-title', 'h1.post-title', 'h1.article-title',
                '.story-headline', '.headline', '.title', 'h1'
            ],
            'content': [
                'article', '.entry-content', '.post-content', '.article-content',
                '.story-body', '.content', '.article-body', 'main .text',
                '.post-body', '[itemprop="articleBody"]'
            ]
        }
    
    def extract_content(self, url: str) -> Optional[Dict]:
        """Extract content with caching and multiple methods"""
        start_time = time.time()
        
        # Check cache
        url_hash = hashlib.md5(url.encode()).hexdigest()
        if url_hash in self.cache:
            self.monitor.log_cache(True)
            return self.cache[url_hash]
        
        self.monitor.log_cache(False)
        
        # Try newspaper3k first if available
        result = None
        if NEWSPAPER_AVAILABLE:
            result = self._extract_with_newspaper(url)
        
        # Fallback to BeautifulSoup
        if not result:
            result = self._extract_with_bs4(url)
        
        # Process result
        if result:
            result['reading_time'] = self._estimate_reading_time(result['content'])
            result['language'] = self._detect_language(result['title'] + ' ' + result['content'][:500])
            
            # Cache successful extraction
            self.cache[url_hash] = result
            self.monitor.log_extraction(True, time.time() - start_time)
        else:
            self.monitor.log_extraction(False, time.time() - start_time)
        
        return result
    
    def _extract_with_newspaper(self, url: str) -> Optional[Dict]:
        """Extract using newspaper3k"""
        try:
            article = Article(url, language='he')
            article.config.browser_user_agent = 'Mozilla/5.0 (compatible; AdvancedBot/1.0)'
            article.config.request_timeout = 15
            
            article.download()
            article.parse()
            
            if article.text and len(article.text.strip()) > 100:
                return {
                    'title': article.title or 'כותרת לא זמינה',
                    'content': article.text.strip(),
                    'authors': article.authors,
                    'publish_date': article.publish_date.isoformat() if article.publish_date else None,
                    'method': 'newspaper3k'
                }
        except Exception as e:
            logger.warning(f"Newspaper extraction failed for {url}: {e}")
        
        return None
    
    def _extract_with_bs4(self, url: str) -> Optional[Dict]:
        """Extract using BeautifulSoup"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'he,en-US;q=0.7,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe', 'noscript']):
                tag.decompose()
            
            title = self._extract_title(soup)
            content = self._extract_content_text(soup)
            
            if title and content and len(content) > 100:
                return {
                    'title': title,
                    'content': content,
                    'authors': [],
                    'publish_date': None,
                    'method': 'beautifulsoup'
                }
                
        except Exception as e:
            logger.warning(f"BeautifulSoup extraction failed for {url}: {e}")
        
        return None
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract title using smart selectors"""
        for selector in self.selectors['title']:
            element = soup.select_one(selector)
            if element and element.get_text().strip():
                title = element.get_text().strip()
                title = re.sub(r'\s+', ' ', title)
                return title[:200]
        
        # Fallback to page title
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text().strip()[:200]
        
        return "כותרת לא זמינה"
    
    def _extract_content_text(self, soup: BeautifulSoup) -> str:
        """Extract main content"""
        for selector in self.selectors['content']:
            element = soup.select_one(selector)
            if element:
                # Clean nested unwanted elements
                for unwanted in element.select('nav, header, footer, .ad, .advertisement'):
                    unwanted.decompose()
                
                text = element.get_text().strip()
                if len(text) > 200:
                    return re.sub(r'\s+', ' ', text)[:5000]
        
        # Fallback: extract all paragraphs
        paragraphs = soup.find_all('p')
        text = ' '.join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 20])
        return text[:5000] if len(text) > 200 else ""
    
    def _detect_language(self, text: str) -> str:
        """Detect text language"""
        if self.hebrew_pattern.search(text):
            return 'he'
        elif self.arabic_pattern.search(text):
            return 'ar'
        return 'en'
    
    def _estimate_reading_time(self, text: str) -> int:
        """Estimate reading time in minutes"""
        words = len(text.split())
        # Average reading speed: 200 words per minute
        return max(1, round(words / 200))

class SmartCategorizer:
    """Intelligent article categorization"""
    
    def __init__(self):
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
                'מניות', 'ביטקוין', 'בנק', 'אינפלציה', 'משכורת', 'מס',
                'נדלן', 'הלוואה', 'חוב'
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
        
        # Weight different parts of the text
        self.weights = {
            'title': 3.0,
            'first_paragraph': 2.0,
            'content': 1.0
        }
    
    def categorize(self, title: str, content: str) -> str:
        """Categorize article based on content"""
        # Split content into parts
        paragraphs = content.split('\n\n')
        first_paragraph = paragraphs[0] if paragraphs else ""
        
        text_parts = {
            'title': title.lower(),
            'first_paragraph': first_paragraph.lower(),
            'content': content.lower()
        }
        
        category_scores = {}
        
        for category, keywords in self.categories.items():
            score = 0
            
            for text_type, text in text_parts.items():
                weight = self.weights[text_type]
                keyword_count = sum(1 for keyword in keywords if keyword.lower() in text)
                score += keyword_count * weight
            
            if score > 0:
                category_scores[category] = score
        
        if category_scores:
            return max(category_scores, key=category_scores.get)
        
        return 'כללי'

class AdvancedSummarizer:
    """Smart text summarization"""
    
    def __init__(self):
        self.hebrew_stopwords = {
            'של', 'את', 'על', 'אל', 'עם', 'כל', 'כי', 'אם', 'לא', 'או', 'גם', 'רק',
            'אבל', 'אך', 'כך', 'כן', 'לכן', 'אז', 'שם', 'פה', 'זה', 'זו', 'הוא', 'היא',
            'אני', 'אתה', 'אנחנו', 'אתם', 'הם', 'הן', 'יש', 'יהיה', 'היה', 'להיות'
        }
    
    def summarize(self, text: str, max_length: int = 300) -> str:
        """Create intelligent summary"""
        try:
            sentences = self._split_sentences(text)
            
            if len(sentences) <= 2:
                return '. '.join(sentences)
            
            # Score sentences
            scored_sentences = self._score_sentences(sentences, text)
            
            # Select best sentences
            selected = self._select_sentences(scored_sentences, max_length)
            
            # Sort by original order and join
            selected.sort(key=lambda x: x[2])  # Sort by original position
            summary = '. '.join([s[0] for s in selected])
            
            return summary if len(summary) <= max_length else summary[:max_length] + "..."
            
        except Exception as e:
            logger.error(f"Summarization error: {e}")
            # Fallback to simple truncation
            sentences = text.split('.')[:2]
            return '. '.join(sentences).strip() + "."
    
    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Handle Hebrew and English punctuation
        sentences = re.split(r'[.!?]+\s+', text)
        return [s.strip() for s in sentences if len(s.strip()) > 10]
    
    def _score_sentences(self, sentences: List[str], full_text: str) -> List[Tuple[str, float, int]]:
        """Score sentences by importance"""
        # Calculate word frequencies
        words = re.findall(r'\b\w+\b', full_text.lower())
        word_freq = {}
        for word in words:
            if word not in self.hebrew_stopwords and len(word) > 2:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        scored = []
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
            
            # Length penalty for very short or very long sentences
            if 15 < len(sentence) < 150:
                score *= 1.2
            
            # Keyword bonus
            if any(keyword in sentence.lower() for keyword in ['ראשון', 'עיקרי', 'חשוב', 'מרכזי']):
                score *= 1.3
            
            scored.append((sentence, score, i))
        
        return scored
    
    def _select_sentences(self, scored_sentences: List[Tuple[str, float, int]], max_length: int) -> List[Tuple[str, float, int]]:
        """Select best sentences within length limit"""
        # Sort by score
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        selected = []
        total_length = 0
        
        for sentence_data in scored_sentences:
            sentence, score, position = sentence_data
            if total_length + len(sentence) <= max_length - 50:  # Leave some buffer
                selected.append(sentence_data)
                total_length += len(sentence)
                
                if len(selected) >= 3:  # Max 3 sentences
                    break
        
        return selected if selected else [scored_sentences[0]] if scored_sentences else []

# Initialize components
extractor = SmartContentExtractor()
categorizer = SmartCategorizer()
summarizer = AdvancedSummarizer()
monitor = PerformanceMonitor()

print("🚀 מערכות מתקדמות אותחלו!")
print(f"📰 Newspaper3k: {'✅ זמין' if NEWSPAPER_AVAILABLE else '❌ לא זמין'}")