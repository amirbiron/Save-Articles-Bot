#!/usr/bin/env python3
"""
Simple health check for the optimized Telegram bot
Run this before deployment to catch issues early
"""

import sys
import os

def check_dependencies():
    """Check if all required dependencies are available"""
    required_modules = [
        'telegram',
        'aiohttp',
        'aiosqlite',
        'bs4',
        'cachetools'
    ]
    
    missing = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module}")
        except ImportError:
            missing.append(module)
            print(f"❌ {module}")
    
    return missing

def check_environment():
    """Check environment variables"""
    required_env = ['TELEGRAM_TOKEN']
    missing = []
    
    for env_var in required_env:
        if env_var in os.environ:
            print(f"✅ {env_var} is set")
        else:
            missing.append(env_var)
            print(f"⚠️ {env_var} not set (will use default)")
    
    return missing

def check_bot_syntax():
    """Check if bot.py has syntax errors"""
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        compile(content, 'bot.py', 'exec')
        print("✅ bot.py syntax is valid")
        return True
    except SyntaxError as e:
        print(f"❌ Syntax error in bot.py: {e}")
        return False
    except FileNotFoundError:
        print("❌ bot.py not found")
        return False

def main():
    """Run all health checks"""
    print("🔍 Running deployment health checks...\n")
    
    print("📦 Checking dependencies:")
    missing_deps = check_dependencies()
    
    print("\n🌍 Checking environment:")
    missing_env = check_environment()
    
    print("\n🐍 Checking Python syntax:")
    syntax_ok = check_bot_syntax()
    
    print("\n" + "="*50)
    
    if missing_deps:
        print("❌ Missing dependencies. Run: pip install -r requirements.txt")
        return False
    
    if not syntax_ok:
        print("❌ Syntax errors found. Fix before deploying.")
        return False
    
    print("✅ All checks passed! Ready for deployment.")
    print("\n🚀 To deploy:")
    print("1. Set TELEGRAM_TOKEN environment variable")
    print("2. Run: python bot.py")
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)