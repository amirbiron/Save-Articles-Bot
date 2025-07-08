#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Bot Database & Main Functions
Part 2 of the advanced bot system
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
from dataclasses import asdict

class AdvancedDatabase:
    """Advanced database with analytics and user management"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
        print("✅ מסד נתונים מתקדם מוכן!")
    
    def init_database(self):
        """Initialize advanced database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Articles table with advanced fields
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
                tags TEXT DEFAULT '',
                date_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_read TIMESTAMP,
                is_favorite BOOLEAN DEFAULT 0,
                view_count INTEGER DEFAULT 0,
                extraction_method TEXT DEFAULT 'unknown'
            )
        ''')
        
        # User statistics table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                articles_saved INTEGER DEFAULT 0,
                articles_read INTEGER DEFAULT 0,
                favorite_category TEXT DEFAULT 'כללי',
                total_reading_time INTEGER DEFAULT 0,
                first_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                preferences TEXT DEFAULT '{}'
            )
        ''')
        
        # Reading sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reading_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                article_id INTEGER NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT 0,
                FOREIGN KEY (article_id) REFERENCES articles (id)
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_articles ON articles(user_id, date_saved)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_category ON articles(category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_article_language ON articles(language)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_stats ON user_stats(user_id)')
        
        conn.commit()
        conn.close()
    
    def save_article(self, user_id: int, url: str, title: str, summary: str, 
                    content: str, category: str = 'כללי', language: str = 'he',
                    reading_time: int = 1, extraction_method: str = 'unknown') -> int:
        """Save article with advanced metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO articles (user_id, url, title, summary, content, category, 
                                language, reading_time, extraction_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, url, title, summary, content, category, language, reading_time, extraction_method))
        
        article_id = cursor.lastrowid
        
        # Update user statistics
        cursor.execute('''
            INSERT OR REPLACE INTO user_stats (user_id, articles_saved, last_activity)
            VALUES (?, COALESCE((SELECT articles_saved FROM user_stats WHERE user_id = ?), 0) + 1, ?)
        ''', (user_id, user_id, datetime.now()))
        
        conn.commit()
        conn.close()
        return article_id
    
    def get_user_articles(self, user_id: int, category: str = None, 
                         limit: int = 20, offset: int = 0, 
                         sort_by: str = 'date_saved') -> List[Dict]:
        """Get user articles with advanced filtering"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        base_query = '''
            SELECT id, url, title, summary, category, language, reading_time,
                   date_saved, date_read, is_favorite, view_count
            FROM articles 
            WHERE user_id = ?
        '''
        
        params = [user_id]
        
        if category:
            base_query += ' AND category = ?'
            params.append(category)
        
        # Add sorting
        if sort_by == 'date_saved':
            base_query += ' ORDER BY date_saved DESC'
        elif sort_by == 'reading_time':
            base_query += ' ORDER BY reading_time ASC'
        elif sort_by == 'category':
            base_query += ' ORDER BY category, date_saved DESC'
        
        base_query += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        cursor.execute(base_query, params)
        articles = cursor.fetchall()
        
        # Convert to dictionaries
        columns = ['id', 'url', 'title', 'summary', 'category', 'language', 
                  'reading_time', 'date_saved', 'date_read', 'is_favorite', 'view_count']
        
        result = []
        for article in articles:
            article_dict = dict(zip(columns, article))
            result.append(article_dict)
        
        conn.close()
        return result
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Get comprehensive user statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Basic stats
        cursor.execute('''
            SELECT COUNT(*) as total_articles,
                   COUNT(CASE WHEN date_read IS NOT NULL THEN 1 END) as read_articles,
                   COUNT(CASE WHEN is_favorite = 1 THEN 1 END) as favorite_articles,
                   AVG(reading_time) as avg_reading_time,
                   SUM(reading_time) as total_reading_time
            FROM articles WHERE user_id = ?
        ''', (user_id,))
        
        basic_stats = cursor.fetchone()
        
        # Category breakdown
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM articles 
            WHERE user_id = ? 
            GROUP BY category 
            ORDER BY count DESC
        ''', (user_id,))
        
        categories = dict(cursor.fetchall())
        
        # Language breakdown
        cursor.execute('''
            SELECT language, COUNT(*) as count 
            FROM articles 
            WHERE user_id = ? 
            GROUP BY language
        ''', (user_id,))
        
        languages = dict(cursor.fetchall())
        
        # Activity by month
        cursor.execute('''
            SELECT strftime('%Y-%m', date_saved) as month, COUNT(*) as count
            FROM articles 
            WHERE user_id = ? 
            GROUP BY month 
            ORDER BY month DESC 
            LIMIT 6
        ''', (user_id,))
        
        monthly_activity = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'total_articles': basic_stats[0] or 0,
            'read_articles': basic_stats[1] or 0,
            'favorite_articles': basic_stats[2] or 0,
            'avg_reading_time': round(basic_stats[3] or 0, 1),
            'total_reading_time': basic_stats[4] or 0,
            'categories': categories,
            'languages': languages,
            'monthly_activity': monthly_activity,
            'reading_completion_rate': round((basic_stats[1] or 0) / max(basic_stats[0] or 1, 1) * 100, 1)
        }
    
    def mark_as_read(self, article_id: int, user_id: int):
        """Mark article as read"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE articles 
            SET date_read = ?, view_count = view_count + 1
            WHERE id = ? AND user_id = ?
        ''', (datetime.now(), article_id, user_id))
        
        conn.commit()
        conn.close()
    
    def toggle_favorite(self, article_id: int, user_id: int) -> bool:
        """Toggle article favorite status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT is_favorite FROM articles WHERE id = ? AND user_id = ?', 
                      (article_id, user_id))
        current = cursor.fetchone()
        
        if current:
            new_status = not bool(current[0])
            cursor.execute('''
                UPDATE articles 
                SET is_favorite = ?
                WHERE id = ? AND user_id = ?
            ''', (new_status, article_id, user_id))
            
            conn.commit()
            conn.close()
            return new_status
        
        conn.close()
        return False
    
    def delete_article(self, article_id: int, user_id: int):
        """Delete article"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', 
                      (article_id, user_id))
        cursor.execute('DELETE FROM reading_sessions WHERE article_id = ? AND user_id = ?',
                      (article_id, user_id))
        
        conn.commit()
        conn.close()
    
    def search_articles(self, user_id: int, query: str, limit: int = 10) -> List[Dict]:
        """Search articles by title and content"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        search_query = f"%{query}%"
        cursor.execute('''
            SELECT id, title, summary, category, date_saved
            FROM articles 
            WHERE user_id = ? AND (title LIKE ? OR summary LIKE ? OR content LIKE ?)
            ORDER BY date_saved DESC
            LIMIT ?
        ''', (user_id, search_query, search_query, search_query, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        columns = ['id', 'title', 'summary', 'category', 'date_saved']
        return [dict(zip(columns, row)) for row in results]

# Initialize database
db = AdvancedDatabase("read_later_advanced.db")
print("🗄️ מסד נתונים מתקדם מוכן!")