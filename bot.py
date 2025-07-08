import logging
import sqlite3
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
import os

from dataclasses import dataclass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# הגדרות
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# קונפיג
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
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
    def __init__(self):
        self.init_database()

    def init_database(self):
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

    def summarize_text(self, text: str, max_length: int = 150) -> str:
        try:
            sentences = text.split('.')[:3]
            summary = '. '.join(sentences).strip()
            return summary[:max_length] + "..." if len(summary) > max_length else summary
        except:
            return "סיכום לא זמין"

    def save_article(self, user_id: int, url: str, title: str, summary: str, full_text: str,
                     category: str = 'כללי', tags: str = '') -> int:
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

    def get_user_articles(self, user_id: int) -> List[SavedArticle]:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM articles WHERE user_id = ? ORDER BY date_saved DESC', (user_id,))
        articles = [SavedArticle(*row) for row in cursor.fetchall()]
        conn.close()
        return articles

    def delete_article(self, article_id: int, user_id: int):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM articles WHERE id = ? AND user_id = ?', (article_id, user_id))
        conn.commit()
        conn.close()

bot = ReadLaterBot()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("📚 רשימת כתבות"), KeyboardButton("📖 כתבות שלי")],
        [KeyboardButton("💾 גיבוי"), KeyboardButton("🔍 חיפוש")],
        [KeyboardButton("🆘 עזרה"), KeyboardButton("📊 סטטיסטיקות")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, persistent=True)

    await update.message.reply_text("✅ הבוט פועל! שלח לי קישור לכתבה", reply_markup=reply_markup)

async def saved_articles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    articles = bot.get_user_articles(user_id)
    if not articles:
        await update.message.reply_text("אין לך כתבות שמורות עדיין.")
        return

    response = f"📚 כתבות שמורות ({len(articles)}):\n"
    for i, article in enumerate(articles[:10], 1):
        response += f"{i}. {article.title[:50]}...\n"
    await update.message.reply_text(response)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data.startswith("delete_"):
        article_id = int(data.split("_")[1])
        bot.delete_article(article_id, user_id)
        await query.edit_message_text("🗑️ נמחק בהצלחה")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔗 שלח לי קישור תקני לכתבה!")

def main():
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN לא מוגדר בסביבה!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("saved", saved_articles))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🚀 הבוט מופעל (polling)...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
