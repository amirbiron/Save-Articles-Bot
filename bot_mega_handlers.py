#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 MEGA ADVANCED BOT - Part 2: Handlers & Database Functions
המשך הבוט המתקדם עם כל הפונקציות
"""

import sqlite3
import re
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from bot_mega_advanced import MegaAdvancedBot, TELEGRAM_TOKEN, DB_PATH

# Initialize the mega bot
mega_bot = MegaAdvancedBot()

class DatabaseFunctions:
    """פונקציות מסד נתונים מתקדמות"""
    
    @staticmethod
    def get_user_articles(user_id: int, limit: int = 15, category: str = None) -> List:
        """קבלת מאמרים של משתמש"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if category:
            cursor.execute('''
                SELECT id, title, summary, category, language, reading_time, 
                       date_saved, date_read, is_favorite, view_count
                FROM articles 
                WHERE user_id = ? AND category = ?
                ORDER BY date_saved DESC 
                LIMIT ?
            ''', (user_id, category, limit))
        else:
            cursor.execute('''
                SELECT id, title, summary, category, language, reading_time,
                       date_saved, date_read, is_favorite, view_count
                FROM articles 
                WHERE user_id = ?
                ORDER BY date_saved DESC 
                LIMIT ?
            ''', (user_id, limit))
        
        articles = cursor.fetchall()
        conn.close()
        return articles
    
    @staticmethod
    def get_user_stats(user_id: int) -> Dict:
        """סטטיסטיקות משתמש מתקדמות"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # סטטיסטיקות בסיסיות
        cursor.execute('''
            SELECT 
                COUNT(*) as total_articles,
                COUNT(CASE WHEN date_read IS NOT NULL THEN 1 END) as read_articles,
                COUNT(CASE WHEN is_favorite = 1 THEN 1 END) as favorite_articles,
                AVG(reading_time) as avg_reading_time,
                SUM(reading_time) as total_reading_time
            FROM articles 
            WHERE user_id = ?
        ''', (user_id,))
        
        basic_stats = cursor.fetchone()
        
        # פילוח לפי קטגוריות
        cursor.execute('''
            SELECT category, COUNT(*) as count 
            FROM articles 
            WHERE user_id = ? 
            GROUP BY category 
            ORDER BY count DESC
        ''', (user_id,))
        
        categories = dict(cursor.fetchall())
        
        # פילוח לפי שפות
        cursor.execute('''
            SELECT language, COUNT(*) as count 
            FROM articles 
            WHERE user_id = ? 
            GROUP BY language
        ''', (user_id,))
        
        languages = dict(cursor.fetchall())
        
        conn.close()
        
        total_articles = basic_stats[0] or 0
        read_articles = basic_stats[1] or 0
        
        return {
            'total_articles': total_articles,
            'read_articles': read_articles,
            'favorite_articles': basic_stats[2] or 0,
            'avg_reading_time': round(basic_stats[3] or 0, 1),
            'total_reading_time': basic_stats[4] or 0,
            'reading_completion_rate': round((read_articles / max(total_articles, 1)) * 100, 1),
            'categories': categories,
            'languages': languages
        }
    
    @staticmethod
    def search_articles(user_id: int, query: str, limit: int = 10) -> List:
        """חיפוש במאמרים"""
        conn = sqlite3.connect(DB_PATH)
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
        return results
    
    @staticmethod
    def toggle_favorite(article_id: int, user_id: int) -> bool:
        """החלפת סטטוס מועדף"""
        conn = sqlite3.connect(DB_PATH)
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
    
    @staticmethod
    def mark_as_read(article_id: int, user_id: int):
        """סימון כנקרא"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE articles 
            SET date_read = ?, view_count = view_count + 1
            WHERE id = ? AND user_id = ?
        ''', (datetime.now(), article_id, user_id))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def delete_article(article_id: int, user_id: int):
        """מחיקת מאמר"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', 
                      (article_id, user_id))
        
        conn.commit()
        conn.close()

class MegaHandlers:
    """טיפול בפקודות טלגרם מתקדמות"""
    
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """פקודת התחלה מתקדמת"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "משתמש"
        
        print(f"🆕 משתמש התחיל: {user_name} ({user_id})")
        
        welcome_message = f"""
🚀 **ברוך הבא {user_name} לבוט המתקדם ביותר!**

🎯 **תכונות מהפכניות:**
• 🧠 חילוץ תוכן חכם עם AI
• 📊 מיון אוטומטי ל-7 קטגוריות
• 🎯 סיכומים חכמים ומותאמים אישית
• 📈 ניתוח סטטיסטיקות מתקדם
• 🔍 חיפוש מהיר וחכם
• ⭐ מערכת מועדפים
• 🌐 תמיכה בעברית, אנגלית וערבית
• 💾 מטמון מהיר לביצועים מיטביים

📝 **איך להתחיל:**
שלח לי קישור לכתבה ותראה את הקסם! ✨

🔗 **פקודות מתקדמות:**
• `/saved` - ספרייה מסודרת
• `/stats` - ניתוח אישי מפורט
• `/search [מילה]` - חיפוש במהירות
• `/categories` - מיון לפי נושאים

**קדימה, בואו נתחיל לבנות את הספרייה הדיגיטלית שלך!** 🚀
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="stats"),
                InlineKeyboardButton("📚 הספרייה שלי", callback_data="saved")
            ],
            [
                InlineKeyboardButton("🔍 חיפוש מתקדם", callback_data="search_help"),
                InlineKeyboardButton("🆘 עזרה מלאה", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    @staticmethod
    async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """עיבוד קישורים מתקדם עם AI"""
        url = update.message.text.strip()
        user_id = update.effective_user.id
        
        print(f"🔗 עיבוד קישור מ-{user_id}: {url}")
        
        # בדיקת URL
        if not re.match(r'https?://', url):
            await update.message.reply_text(
                "❌ זה לא נראה כמו קישור תקין.\n"
                "💡 ודא שהקישור מתחיל ב-http או https\n\n"
                "🎯 **דוגמה נכונה:**\n"
                "`https://www.ynet.co.il/articles/...`",
                parse_mode='Markdown'
            )
            return
        
        # הודעת עיבוד
        loading_msg = await update.message.reply_text(
            "🚀 **מעבד מאמר בטכנולוגיה מתקדמת...**\n\n"
            "⚡ חילוץ תוכן חכם\n"
            "🤖 ניתוח AI\n"
            "📝 יצירת סיכום\n"
            "📊 קביעת קטגוריה"
        )
        
        start_time = time.time()
        
        # חילוץ תוכן מתקדם
        article_data = mega_bot.extract_content(url)
        
        if not article_data:
            await loading_msg.edit_text(
                f"❌ **לא הצלחתי לחלץ תוכן מהמאמר**\n\n"
                f"🔗 **קישור:** {url}\n\n"
                f"💡 **סיבות אפשריות:**\n"
                f"• האתר חוסם בוטים אוטומטיים\n"
                f"• המאמר מוגן בתשלום או רישום\n"
                f"• בעיה זמנית בשרת\n"
                f"• הקישור לא מוביל למאמר\n\n"
                f"🔄 **מה לעשות:**\n"
                f"• נסה קישור ישיר למאמר\n"
                f"• בדוק שהקישור עובד בדפדפן\n"
                f"• נסה שוב מאוחר יותר"
            )
            return
        
        # עדכון סטטוס
        await loading_msg.edit_text("🤖 **יוצר סיכום AI וקובע קטגוריה...**")
        
        # יצירת סיכום וקביעת קטגוריה
        summary = mega_bot.smart_summarize(article_data['content'])
        category = mega_bot.categorize_article(article_data['title'], article_data['content'])
        
        # שמירה במסד נתונים
        article_id = mega_bot.save_article(
            user_id=user_id,
            url=url,
            title=article_data['title'],
            summary=summary,
            content=article_data['content'],
            category=category,
            language=article_data['language'],
            reading_time=article_data['reading_time'],
            extraction_method=article_data['method']
        )
        
        processing_time = time.time() - start_time
        
        # יצירת תגובה עם כפתורי פעולה
        keyboard = [
            [
                InlineKeyboardButton("⭐ הוסף למועדפים", callback_data=f"fav_{article_id}"),
                InlineKeyboardButton("✅ סמן כנקרא", callback_data=f"read_{article_id}")
            ],
            [
                InlineKeyboardButton(f"📂 עוד ב{category}", callback_data=f"cat_{category}"),
                InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats")
            ],
            [
                InlineKeyboardButton("🔍 חיפוש דומים", callback_data=f"search_{category}"),
                InlineKeyboardButton("🗑️ מחק", callback_data=f"delete_{article_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # קביעת אמוג'י לפי שיטת חילוץ
        method_emoji = "📰" if article_data['method'] == 'newspaper3k' else "🔧"
        
        response_text = f"""
✅ **מאמר נשמר בהצלחה בספרייה הדיגיטלית!**

📰 **כותרת:** {article_data['title']}
📂 **קטגוריה:** {category}
🌐 **שפה:** {article_data['language']}
⏱️ **זמן קריאה:** {article_data['reading_time']} דקות
{method_emoji} **שיטת חילוץ:** {article_data['method']}

📝 **סיכום חכם:**
{summary}

🔗 [קישור למאמר המלא]({url})

⚡ **זמן עיבוד:** {processing_time:.2f} שניות
💾 **מזהה מאמר:** #{article_id}
"""
        
        await loading_msg.edit_text(
            response_text, 
            reply_markup=reply_markup, 
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        print(f"✅ מאמר נשמר: {article_data['title'][:50]}... עבור {user_id}")
    
    @staticmethod
    async def saved_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """הצגת מאמרים שמורים מתקדמת"""
        user_id = update.effective_user.id
        articles = DatabaseFunctions.get_user_articles(user_id, limit=15)
        
        if not articles:
            keyboard = [
                [InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="stats")],
                [InlineKeyboardButton("🎯 איך להתחיל?", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 **הספרייה הדיגיטלית שלך ריקה**\n\n"
                "🚀 **איך להתחיל:**\n"
                "• שלח קישור למאמר מעניין\n"
                "• הבוט יעבד אותו באופן חכם\n"
                "• יווצר סיכום ויקבע קטגוריה\n"
                "• המאמר יישמר בספרייה שלך\n\n"
                "💡 **מוכן לבנות את הספרייה הראשונה שלך?**",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # ארגון לפי קטגוריות
        categories = {}
        for article in articles:
            cat = article[3]  # category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(article)
        
        response = f"📚 **הספרייה הדיגיטלית שלך** ({len(articles)} מאמרים אחרונים):\n\n"
        
        for category, cat_articles in categories.items():
            response += f"📂 **{category}** ({len(cat_articles)} מאמרים)\n"
            
            for i, article in enumerate(cat_articles[:3], 1):
                title = article[1][:45] + "..." if len(article[1]) > 45 else article[1]
                
                # אינדיקטורים
                read_emoji = "✅" if article[7] else "⏳"  # date_read
                fav_emoji = "⭐" if article[8] else ""    # is_favorite
                
                date = article[6][:10]  # date_saved
                reading_time = article[5]  # reading_time
                language = article[4]  # language
                
                response += f"{read_emoji} {i}. {title} {fav_emoji}\n"
                response += f"   📅 {date} • ⏱️ {reading_time} דקות • 🌐 {language}\n"
            
            if len(cat_articles) > 3:
                response += f"   ... ועוד {len(cat_articles) - 3} מאמרים\n"
            response += "\n"
        
        # כפתורי פעולה
        keyboard = [
            [
                InlineKeyboardButton("📊 סטטיסטיקות מלאות", callback_data="stats"),
                InlineKeyboardButton("🔍 חיפוש מתקדם", callback_data="search_help")
            ],
            [
                InlineKeyboardButton("⭐ מועדפים בלבד", callback_data="favorites"),
                InlineKeyboardButton("📂 מיון קטגוריות", callback_data="categories")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
    
    @staticmethod
    async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """סטטיסטיקות משתמש מתקדמות"""
        user_id = update.effective_user.id
        stats = DatabaseFunctions.get_user_stats(user_id)
        
        if stats['total_articles'] == 0:
            await update.message.reply_text(
                "📊 **הסטטיסטיקות שלך**\n\n"
                "🆕 עדיין לא שמרת מאמרים.\n"
                "שלח קישור למאמר כדי להתחיל לבנות נתונים!"
            )
            return
        
        # חישוב נתונים נוספים
        total_hours = stats['total_reading_time'] / 60
        system_stats = mega_bot.performance_stats
        uptime_hours = (time.time() - system_stats['start_time']) / 3600
        
        stats_text = f"""
📊 **דשבורד אישי מתקדם**

📈 **סטטיסטיקות כלליות:**
• 📚 סה"כ מאמרים: {stats['total_articles']}
• ✅ מאמרים שנקראו: {stats['read_articles']}
• ⭐ מאמרים מועדפים: {stats['favorite_articles']}
• 📖 אחוז השלמת קריאה: {stats['reading_completion_rate']}%

⏱️ **זמני קריאה:**
• זמן קריאה כולל: {stats['total_reading_time']} דקות
• ממוצע למאמר: {stats['avg_reading_time']} דקות
• שעות קריאה: {total_hours:.1f} שעות

📂 **פילוח קטגוריות:**
"""
        
        # הוספת פילוח קטגוריות
        for category, count in stats['categories'].items():
            percentage = (count / stats['total_articles'] * 100)
            bar = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
            stats_text += f"• {category}: {count} ({percentage:.1f}%) {bar}\n"
        
        if stats['languages']:
            stats_text += f"\n🌐 **שפות:**\n"
            for lang, count in stats['languages'].items():
                stats_text += f"• {lang}: {count} מאמרים\n"
        
        # נתוני ביצועים
        success_rate = (system_stats['successful_extractions'] / max(system_stats['articles_processed'], 1)) * 100
        avg_processing_time = system_stats['total_processing_time'] / max(system_stats['articles_processed'], 1)
        
        stats_text += f"""
⚡ **ביצועי המערכת:**
• מאמרים מעובדים: {system_stats['articles_processed']}
• שיעור הצלחה: {success_rate:.1f}%
• זמן עיבוד ממוצע: {avg_processing_time:.2f} שניות
• פגיעות מטמון: {system_stats['cache_hits']}/{system_stats['cache_hits'] + system_stats['cache_misses']}
• זמן פעילות: {uptime_hours:.1f} שעות
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📂 פירוט קטגוריות", callback_data="categories"),
                InlineKeyboardButton("⭐ מועדפים", callback_data="favorites")
            ],
            [
                InlineKeyboardButton("🔄 רענן נתונים", callback_data="stats"),
                InlineKeyboardButton("📈 ניתוח מתקדם", callback_data="advanced_stats")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    @staticmethod
    async def search_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """חיפוש מתקדם במאמרים"""
        if not context.args:
            await update.message.reply_text(
                "🔍 **חיפוש מתקדם במאמרים**\n\n"
                "📝 **שימוש:** `/search [מילת חיפוש]`\n\n"
                "🎯 **דוגמאות:**\n"
                "• `/search טכנולוגיה` - כל מאמרי הטכנולוגיה\n"
                "• `/search בינה מלאכותית` - מאמרים על AI\n"
                "• `/search קורונה` - מאמרים רפואיים\n"
                "• `/search השקעות` - מאמרים כלכליים\n\n"
                "💡 **טיפ:** החיפוש פועל על כותרות, סיכומים ותוכן מלא!",
                parse_mode='Markdown'
            )
            return
        
        user_id = update.effective_user.id
        query = ' '.join(context.args)
        
        print(f"🔍 חיפוש: '{query}' עבור {user_id}")
        
        results = DatabaseFunctions.search_articles(user_id, query, limit=10)
        
        if not results:
            await update.message.reply_text(
                f"🔍 **לא נמצאו תוצאות עבור:** `{query}`\n\n"
                "💡 **נסה:**\n"
                "• מילות חיפוש אחרות או קצרות יותר\n"
                "• חיפוש באנגלית אם המאמר באנגלית\n"
                "• חיפוש לפי קטגוריה כללית\n"
                "• בדוק שכתבת נכון\n\n"
                "🎯 **דוגמאות מוצלחות:**\n"
                "• `בריאות` `כלכלה` `טכנולוגיה`\n"
                "• `ביטקוין` `קורונה` `בינה מלאכותית`",
                parse_mode='Markdown'
            )
            return
        
        response = f"🔍 **תוצאות חיפוש עבור:** `{query}`\n📊 **נמצאו {len(results)} תוצאות:**\n\n"
        
        for i, article in enumerate(results, 1):
            title = article[1][:55] + "..." if len(article[1]) > 55 else article[1]
            summary = article[2][:75] + "..." if len(article[2]) > 75 else article[2]
            category = article[3]
            date = article[4][:10]
            
            response += f"**{i}. {title}**\n"
            response += f"📂 {category} • 📅 {date}\n"
            response += f"📝 {summary}\n\n"
        
        if len(results) == 10:
            response += "💡 מוצגות 10 התוצאות הראשונות בלבד"
        
        keyboard = [
            [InlineKeyboardButton("🔍 חיפוש חדש", callback_data="search_help")],
            [InlineKeyboardButton("📚 חזרה לספרייה", callback_data="saved")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
    
    @staticmethod
    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """טיפול בכל כפתורי הפעולה"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        print(f"🔘 כפתור נלחץ: {data} על ידי {user_id}")
        
        if data.startswith("delete_"):
            article_id = int(data.split("_")[1])
            DatabaseFunctions.delete_article(article_id, user_id)
            await query.edit_message_text("🗑️ המאמר נמחק בהצלחה מהספרייה!")
            
        elif data.startswith("fav_"):
            article_id = int(data.split("_")[1])
            is_favorite = DatabaseFunctions.toggle_favorite(article_id, user_id)
            status = "נוסף למועדפים" if is_favorite else "הוסר מהמועדפים"
            await query.edit_message_reply_markup()
            await query.message.reply_text(f"⭐ המאמר {status}!")
            
        elif data.startswith("read_"):
            article_id = int(data.split("_")[1])
            DatabaseFunctions.mark_as_read(article_id, user_id)
            await query.edit_message_reply_markup()
            await query.message.reply_text("✅ המאמר סומן כנקרא! עודכנו הסטטיסטיקות שלך.")
            
        elif data == "stats":
            await MegaHandlers.user_stats(update, context)
            
        elif data == "saved":
            await MegaHandlers.saved_articles(update, context)
            
        elif data == "help":
            await MegaHandlers.help_command(update, context)
            
        elif data == "search_help":
            await query.edit_message_text(
                "🔍 **חיפוש מתקדם**\n\n"
                "שלח: `/search [מילת חיפוש]`\n\n"
                "דוגמאות:\n"
                "• `/search טכנולוגיה`\n"
                "• `/search בינה מלאכותית`\n"
                "• `/search בריאות`"
            )
    
    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """מדריך עזרה מקיף"""
        help_text = """
🆘 **מדריך שימוש מקיף לבוט המתקדם**

📝 **פקודות בסיסיות:**
• `/start` - התחלה והיכרות עם הבוט
• `/help` - מדריך מפורט זה
• `/saved` - הצגת הספרייה הדיגיטלית
• `/stats` - דשבורד סטטיסטיקות אישי

🔍 **פקודות מתקדמות:**
• `/search [מילה]` - חיפוש חכם במאמרים
• `/categories` - מיון לפי קטגוריות
• `/favorites` - מאמרים מועדפים בלבד
• `/recent` - מאמרים אחרונים

📊 **7 קטגוריות חכמות:**
• 🔬 טכנולוגיה - AI, סייבר, חדשנות
• 🏥 בריאות - רפואה, תזונה, פסיכולוגיה
• 💰 כלכלה - השקעות, עסקים, קריפטו
• 🏛️ פוליטיקה - ממשל, חוקים, מדיניות
• ⚽ ספורט - כדורגל, אולימפיאדה, כושר
• 🎭 תרבות - אמנות, מוזיקה, קולנוע
• 💡 השראה - מוטיבציה, פיתוח אישי

🎯 **טיפים מתקדמים:**
• הבוט זוהה אוטומטית את השפה (עברית/אנגלית/ערבית)
• השתמש בכפתורי ⭐ לסימון מועדפים
• המערכת זוכרת מה קראת ומה לא
• החיפוש פועל על כותרות, סיכומים ותוכן מלא
• יש מטמון מהיר לביצועים מיטביים

💡 **דוגמאות לשימוש:**
• שלח קישור מynet, walla, haaretz וכו'
• `/search בינה מלאכותית` - מאמרי AI
• `/search השקעות ביטקוין` - מאמרים כלכליים

🚀 **מה המיוחד בבוט הזה:**
• חילוץ תוכן חכם עם כמה שיטות
• סיכומים באמצעות אלגוריתמי NLP
• ניתוח והבנה של תוכן בעברית
• מסד נתונים מתקדם עם אינדקסים
• ביצועים מהירים עם מטמון
• ממשק ידידותי ואינטואיטיבי

❓ **שאלות נפוצות:**
• הבוט עובד עם כל אתר חדשות
• התוכן נשמר באופן מקומי ובטוח
• אין הגבלה על כמות המאמרים
• הכל חינם ללא פרסומות!
"""
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    """הפעלת הבוט המתקדם"""
    print("🚀 מתחיל את הבוט המתקדם ביותר...")
    print(f"🔑 טוקן: {TELEGRAM_TOKEN[:10]}...")
    
    # יצירת אפליקציה
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # הוספת handlers
    application.add_handler(CommandHandler("start", MegaHandlers.start))
    application.add_handler(CommandHandler("help", MegaHandlers.help_command))
    application.add_handler(CommandHandler("saved", MegaHandlers.saved_articles))
    application.add_handler(CommandHandler("stats", MegaHandlers.user_stats))
    application.add_handler(CommandHandler("search", MegaHandlers.search_articles))
    
    # URL handler
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, MegaHandlers.handle_url)
    )
    
    # Button handler
    application.add_handler(CallbackQueryHandler(MegaHandlers.button_callback))
    
    print("✅ כל המערכות מוכנות!")
    print("📡 מתחיל לקבל הודעות...")
    print("🎯 הבוט המתקדם ביותר פעיל!")
    
    # הפעלת הבוט
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()