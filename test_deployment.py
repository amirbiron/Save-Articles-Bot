#!/usr/bin/env python3
"""
Test deployment script - verifies everything works before going live
"""

import os
import sys
import subprocess

def clean_pip_cache():
    """Clean pip cache to avoid old/corrupted files"""
    try:
        subprocess.run(['pip', 'cache', 'purge'], check=True, capture_output=True)
        print("✅ Pip cache cleaned")
    except:
        print("⚠️ Could not clean pip cache (not critical)")

def install_requirements():
    """Install requirements with clean cache"""
    try:
        # Force reinstall to avoid cached issues
        result = subprocess.run([
            'pip', 'install', '-r', 'requirements.txt', 
            '--no-cache-dir', '--force-reinstall'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Requirements installed successfully")
            return True
        else:
            print("❌ Failed to install requirements:")
            print(result.stderr)
            return False
    except Exception as e:
        print(f"❌ Error installing requirements: {e}")
        return False

def test_imports():
    """Test if all imports work"""
    try:
        import telegram
        import aiohttp
        import aiosqlite
        import bs4
        import cachetools
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_bot_syntax():
    """Test bot.py syntax"""
    try:
        with open('bot.py', 'r') as f:
            compile(f.read(), 'bot.py', 'exec')
        print("✅ Bot syntax valid")
        return True
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        return False

def main():
    print("🧪 Testing deployment...\n")
    
    # Step 1: Clean cache
    clean_pip_cache()
    
    # Step 2: Install requirements
    if not install_requirements():
        return False
    
    # Step 3: Test imports
    if not test_imports():
        return False
    
    # Step 4: Test syntax
    if not test_bot_syntax():
        return False
    
    print("\n🎉 Deployment test passed!")
    print("Ready to deploy with: python bot.py")
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)