#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Bot Telegram Handlers
Part 3 of the advanced bot system - All Telegram commands and interactions
"""

import re
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Import our components (assuming they're in the same directory)
from bot_advanced import extractor, categorizer, summarizer, monitor, TELEGRAM_TOKEN
from bot_advanced_db import db

class AdvancedBotHandlers:
    """All Telegram command handlers for the advanced bot"""
    
    @staticmethod
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with user onboarding"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "משתמש"
        
        print(f"🆕 משתמש חדש התחיל: {user_name} ({user_id})")
        
        welcome_message = f"""
🤖 שלום {user_name}! ברוך הבא לבוט המתקדם "שמור לי לקרוא אחר כך"

🚀 **תכונות מתקדמות:**
• 📊 זיהוי קטגוריות אוטומטי
• 🎯 סיכומים חכמים
• 📈 סטטיסטיקות אישיות
• 🔍 חיפוש במאמרים
• ⭐ מועדפים וקריאה מאוחרת
• 🌐 תמיכה במספר שפות

📝 **איך זה עובד:**
• שלח לי קישור לכתבה - אעבד ואשמור
• /saved - הצגת מאמרים שמורים
• /stats - הסטטיסטיקות שלך
• /categories - מאמרים לפי קטגוריות
• /search [מילה] - חיפוש במאמרים

קדימה, שלח לי קישור! 🚀
"""
        
        keyboard = [
            [InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="stats")],
            [InlineKeyboardButton("📚 מאמרים שמורים", callback_data="saved")],
            [InlineKeyboardButton("🆘 עזרה מלאה", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    
    @staticmethod
    async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comprehensive help command"""
        help_text = """
🆘 **מדריך שימוש מלא**

📝 **פקודות בסיסיות:**
• `/start` - התחלה והיכרות
• `/help` - מדריך זה
• `/saved` - מאמרים שמורים
• `/stats` - סטטיסטיקות אישיות

🔍 **פקודות מתקדמות:**
• `/categories` - מאמרים לפי קטגוריות
• `/search [מילת חיפוש]` - חיפוש במאמרים
• `/favorites` - מאמרים מועדפים
• `/recent` - מאמרים אחרונים
• `/performance` - ביצועי המערכת

📊 **קטגוריות זמינות:**
• טכנולוגיה • בריאות • כלכלה • פוליטיקה 
• ספורט • תרבות • השראה • כללי

🎯 **טיפים:**
• שלח קישורים מכל אתר חדשות
• השתמש בכפתורי ⭐ לסימון מועדפים
• המערכת זוכרת מה קראת ומה לא
• החיפוש עובד על כותרות ותוכן

💡 **דוגמאות שימוש:**
• `/search טכנולוגיה` - חיפוש מאמרי טכנולוגיה
• `/categories בריאות` - כל מאמרי הבריאות
"""
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    @staticmethod
    async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Advanced URL processing with smart extraction"""
        url = update.message.text.strip()
        user_id = update.effective_user.id
        
        print(f"🔗 קישור חדש מ-{user_id}: {url}")
        
        # Validate URL
        if not re.match(r'https?://', url):
            await update.message.reply_text(
                "❌ זה לא נראה כמו קישור תקין.\n"
                "💡 ודא שהקישור מתחיל ב-http או https"
            )
            return
        
        # Show processing message
        loading_msg = await update.message.reply_text("🔄 מעבד מאמר בטכנולוגיה מתקדמת...")
        
        start_time = time.time()
        
        # Extract content using advanced extractor
        article_data = extractor.extract_content(url)
        
        if not article_data:
            await loading_msg.edit_text(
                f"❌ לא הצלחתי לחלץ תוכן מהמאמר\n"
                f"🔗 {url}\n\n"
                f"💡 **סיבות אפשריות:**\n"
                f"• האתר חוסם בוטים\n"
                f"• המאמר מוגן בתשלום\n"
                f"• בעיה זמנית בשרת\n\n"
                f"נסה קישור אחר או נסה שוב מאוחר יותר."
            )
            return
        
        # Update processing status
        await loading_msg.edit_text("🤖 יוצר סיכום חכם וקובע קטגוריה...")
        
        # Generate summary and categorize
        summary = summarizer.summarize(article_data['content'])
        category = categorizer.categorize(article_data['title'], article_data['content'])
        
        # Save to database
        article_id = db.save_article(
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
        
        # Create response with action buttons
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
        
        # Determine extraction method emoji
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
"""
        
        await loading_msg.edit_text(
            response_text, 
            reply_markup=reply_markup, 
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        print(f"✅ מאמר נשמר: {article_data['title'][:50]} עבור {user_id}")
    
    @staticmethod
    async def saved_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display saved articles with advanced filtering"""
        user_id = update.effective_user.id
        articles = db.get_user_articles(user_id, limit=15)
        
        if not articles:
            keyboard = [[InlineKeyboardButton("📊 הסטטיסטיקות שלי", callback_data="stats")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 אין מאמרים שמורים עדיין.\n\n"
                "💡 שלח קישור למאמר כדי להתחיל לבנות את הספרייה שלך!",
                reply_markup=reply_markup
            )
            return
        
        # Group articles by category for better display
        categories = {}
        for article in articles:
            cat = article['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(article)
        
        response = f"📚 **הספרייה שלך** ({len(articles)} מאמרים אחרונים):\n\n"
        
        for category, cat_articles in categories.items():
            response += f"📂 **{category}** ({len(cat_articles)} מאמרים)\n"
            
            for i, article in enumerate(cat_articles[:3], 1):
                title = article['title'][:45] + "..." if len(article['title']) > 45 else article['title']
                
                # Status indicators
                read_emoji = "✅" if article['date_read'] else "⏳"
                fav_emoji = "⭐" if article['is_favorite'] else ""
                
                date = article['date_saved'][:10]
                reading_time = article['reading_time']
                
                response += f"{read_emoji} {i}. {title} {fav_emoji}\n"
                response += f"   📅 {date} • ⏱️ {reading_time} דקות\n"
            
            if len(cat_articles) > 3:
                response += f"   ... ועוד {len(cat_articles) - 3} מאמרים\n"
            response += "\n"
        
        # Add action buttons
        keyboard = [
            [
                InlineKeyboardButton("📊 סטטיסטיקות", callback_data="stats"),
                InlineKeyboardButton("🔍 חיפוש", callback_data="search_help")
            ],
            [
                InlineKeyboardButton("⭐ מועדפים", callback_data="favorites"),
                InlineKeyboardButton("📂 קטגוריות", callback_data="categories")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(response, reply_markup=reply_markup, parse_mode='Markdown')
    
    @staticmethod
    async def user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show comprehensive user statistics"""
        user_id = update.effective_user.id
        stats = db.get_user_stats(user_id)
        
        if stats['total_articles'] == 0:
            await update.message.reply_text(
                "📊 **הסטטיסטיקות שלך**\n\n"
                "🆕 עדיין לא שמרת מאמרים.\n"
                "שלח קישור למאמר כדי להתחיל!"
            )
            return
        
        # Create detailed statistics message
        stats_text = f"""
📊 **הסטטיסטיקות שלך**

📈 **כללי:**
• 📚 מאמרים שמורים: {stats['total_articles']}
• ✅ מאמרים שנקראו: {stats['read_articles']}
• ⭐ מאמרים מועדפים: {stats['favorite_articles']}
• 📖 אחוז השלמת קריאה: {stats['reading_completion_rate']}%

⏱️ **זמני קריאה:**
• זמן קריאה כולל: {stats['total_reading_time']} דקות
• ממוצע למאמר: {stats['avg_reading_time']} דקות
• שעות קריאה: {stats['total_reading_time'] / 60:.1f} שעות

📂 **חלוקה לפי קטגוריות:**
"""
        
        # Add category breakdown
        for category, count in stats['categories'].items():
            percentage = (count / stats['total_articles'] * 100)
            stats_text += f"• {category}: {count} מאמרים ({percentage:.1f}%)\n"
        
        if stats['languages']:
            stats_text += f"\n🌐 **שפות:**\n"
            for lang, count in stats['languages'].items():
                lang_name = {'he': 'עברית', 'en': 'אנגלית', 'ar': 'ערבית'}.get(lang, lang)
                stats_text += f"• {lang_name}: {count} מאמרים\n"
        
        # Add performance data
        system_stats = monitor.get_stats()
        stats_text += f"""
⚡ **ביצועי המערכת:**
• מאמרים מעובדים: {system_stats['articles_processed']}
• שיעור הצלחה: {system_stats['success_rate']:.1f}%
• זמן עיבוד ממוצע: {system_stats['avg_processing_time']:.2f} שניות
• מאמרים לשעה: {system_stats['articles_per_hour']:.1f}
"""
        
        keyboard = [
            [
                InlineKeyboardButton("📂 קטגוריות", callback_data="categories"),
                InlineKeyboardButton("⭐ מועדפים", callback_data="favorites")
            ],
            [InlineKeyboardButton("🔄 רענן סטטיסטיקות", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    @staticmethod
    async def search_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Search articles by keyword"""
        if not context.args:
            await update.message.reply_text(
                "🔍 **חיפוש במאמרים**\n\n"
                "שימוש: `/search [מילת חיפוש]`\n\n"
                "דוגמאות:\n"
                "• `/search טכנולוגיה`\n"
                "• `/search בינה מלאכותית`\n"
                "• `/search קורונה`"
            )
            return
        
        user_id = update.effective_user.id
        query = ' '.join(context.args)
        
        results = db.search_articles(user_id, query, limit=10)
        
        if not results:
            await update.message.reply_text(
                f"🔍 לא נמצאו מאמרים עבור: **{query}**\n\n"
                "💡 נסה:\n"
                "• מילות חיפוש אחרות\n"
                "• חיפוש ברמת קטגוריה\n"
                "• בדוק שכתבת נכון"
            )
            return
        
        response = f"🔍 **תוצאות חיפוש עבור:** {query}\n\n"
        
        for i, article in enumerate(results, 1):
            title = article['title'][:60] + "..." if len(article['title']) > 60 else article['title']
            summary = article['summary'][:80] + "..." if len(article['summary']) > 80 else article['summary']
            
            response += f"{i}. **{title}**\n"
            response += f"   📂 {article['category']} • 📅 {article['date_saved'][:10]}\n"
            response += f"   📝 {summary}\n\n"
        
        if len(results) == 10:
            response += "💡 מוצגות 10 התוצאות הראשונות"
        
        await update.message.reply_text(response, parse_mode='Markdown')
    
    @staticmethod
    async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all button callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data.startswith("delete_"):
            article_id = int(data.split("_")[1])
            db.delete_article(article_id, user_id)
            await query.edit_message_text("🗑️ המאמר נמחק בהצלחה!")
            
        elif data.startswith("fav_"):
            article_id = int(data.split("_")[1])
            is_favorite = db.toggle_favorite(article_id, user_id)
            status = "נוסף למועדפים" if is_favorite else "הוסר מהמועדפים"
            await query.edit_message_reply_markup()
            await query.message.reply_text(f"⭐ המאמר {status}!")
            
        elif data.startswith("read_"):
            article_id = int(data.split("_")[1])
            db.mark_as_read(article_id, user_id)
            await query.edit_message_reply_markup()
            await query.message.reply_text("✅ המאמר סומן כנקרא!")
            
        elif data == "stats":
            await AdvancedBotHandlers.user_stats(update, context)
            
        elif data == "saved":
            await AdvancedBotHandlers.saved_articles(update, context)
            
        elif data == "help":
            await AdvancedBotHandlers.help_command(update, context)
            
        elif data == "search_help":
            await query.edit_message_text(
                "🔍 **חיפוש במאמרים**\n\n"
                "שלח: `/search [מילת חיפוש]`\n\n"
                "דוגמאות:\n"
                "• `/search טכנולוגיה`\n"
                "• `/search בינה מלאכותית`"
            )

def main():
    """Main function to run the advanced bot"""
    print("🚀 מתחיל בוט מתקדם...")
    print(f"🔑 טוקן: {TELEGRAM_TOKEN[:10]}...")
    
    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", AdvancedBotHandlers.start))
    application.add_handler(CommandHandler("help", AdvancedBotHandlers.help_command))
    application.add_handler(CommandHandler("saved", AdvancedBotHandlers.saved_articles))
    application.add_handler(CommandHandler("stats", AdvancedBotHandlers.user_stats))
    application.add_handler(CommandHandler("search", AdvancedBotHandlers.search_articles))
    
    # URL handler
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, AdvancedBotHandlers.handle_url)
    )
    
    # Button handler
    application.add_handler(CallbackQueryHandler(AdvancedBotHandlers.button_callback))
    
    print("✅ הכל מוכן!")
    print("📡 מתחיל לקבל הודעות...")
    
    # Run bot
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()