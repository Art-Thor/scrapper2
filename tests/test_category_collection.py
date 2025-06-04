#!/usr/bin/env python3
"""
Test script to verify category collection improvements work correctly.

This script tests the basic functionality without running the full collection process.
"""

import asyncio
import sys
import os

# Add src to path for imports
sys.path.append('src')

from collect_categories import CategoryCollector
from scraper.funtrivia import FunTriviaScraper

async def test_initialization():
    """Test that the collector can initialize without errors."""
    print("🧪 Testing CategoryCollector initialization...")
    
    try:
        collector = CategoryCollector("config/settings.json")
        print("✅ CategoryCollector initialized successfully")
        return True
    except Exception as e:
        print(f"❌ CategoryCollector initialization failed: {e}")
        return False

async def test_scraper_initialization():
    """Test that the scraper can initialize with improved timeouts."""
    print("🧪 Testing FunTriviaScraper initialization...")
    
    try:
        scraper = FunTriviaScraper("config/settings.json")
        await scraper.initialize()
        print("✅ FunTriviaScraper initialized successfully")
        await scraper.close()
        return True
    except Exception as e:
        print(f"❌ FunTriviaScraper initialization failed: {e}")
        return False

async def test_progress_saving():
    """Test that progress saving and loading works."""
    print("🧪 Testing progress saving/loading...")
    
    try:
        collector = CategoryCollector("config/settings.json")
        
        # Add some test data
        collector.categories_data['raw_domains']['Test'] = 5
        collector.categories_data['raw_topics']['TestTopic'] = 3
        collector.categories_data['category_urls'].add('https://test.com')
        
        # Save progress
        test_progress_file = "test_progress.json"
        collector.save_progress(test_progress_file)
        
        # Create new collector and load progress
        collector2 = CategoryCollector("config/settings.json")
        loaded = collector2.load_progress(test_progress_file)
        
        if loaded and collector2.categories_data['raw_domains']['Test'] == 5:
            print("✅ Progress saving/loading works correctly")
            # Clean up
            os.remove(test_progress_file)
            return True
        else:
            print("❌ Progress data doesn't match")
            return False
            
    except Exception as e:
        print(f"❌ Progress saving/loading failed: {e}")
        return False

async def test_configuration():
    """Test that configuration changes are properly loaded."""
    print("🧪 Testing configuration loading...")
    
    try:
        # Test that the scraper loads the new timeout values
        scraper = FunTriviaScraper("config/settings.json")
        
        expected_timeout = 60000  # Our new page_load timeout
        actual_timeout = scraper.config['scraper']['timeouts']['page_load']
        
        if actual_timeout == expected_timeout:
            print(f"✅ Configuration loaded correctly (page_load timeout: {actual_timeout}ms)")
            return True
        else:
            print(f"❌ Configuration mismatch - expected {expected_timeout}, got {actual_timeout}")
            return False
            
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🔬 Running Category Collection Tests")
    print("=" * 50)
    
    tests = [
        test_initialization,
        test_scraper_initialization,
        test_progress_saving,
        test_configuration
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} crashed: {e}")
            results.append(False)
        print()
    
    print("📊 TEST RESULTS")
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! The improvements are working correctly.")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
    
    return passed == total

if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 