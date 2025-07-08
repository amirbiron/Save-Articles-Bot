#!/bin/bash

# Startup script for optimized Telegram bot
echo "🚀 Starting Optimized Telegram Bot..."

# Set environment variables for better performance
export PYTHONOPTIMIZE=1
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Check if required environment variables are set
if [ -z "$TELEGRAM_TOKEN" ]; then
    echo "❌ Error: TELEGRAM_TOKEN environment variable is not set"
    exit 1
fi

# Start the bot with error handling
python bot.py