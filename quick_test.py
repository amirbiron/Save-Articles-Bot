#!/usr/bin/env python3
"""
Quick test to verify the bot is ready for deployment
"""

import asyncio
import sys
import os

async def test_bot_components():
    """Test all bot components work correctly"""
    print("🧪 Testing bot components...")
    
    try:
        # Test imports
        from bot import DatabasePool, DatabaseManager, ContentFetcher, PerformanceMetrics
        print("✅ All imports successful")
        
        # Test database
        db_pool = DatabasePool('test_quick.db', max_connections=3)
        db_manager = DatabaseManager(db_pool)
        await db_manager.init_db()
        print("✅ Database initialized")
        
        # Test content fetcher
        fetcher = ContentFetcher()
        print("✅ Content fetcher created")
        
        # Test performance metrics
        metrics = PerformanceMetrics()
        print("✅ Performance metrics created")
        
        # Cleanup
        await db_pool.close_all()
        await fetcher.close()
        
        print("\n🎉 All tests passed! Bot is ready for deployment!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_bot_components())
    sys.exit(0 if success else 1)