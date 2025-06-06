#!/usr/bin/env python3
"""
Test script to verify incremental saving functionality.
This will scrape just 1-2 quizzes and verify questions are saved immediately.
"""

import asyncio
import sys
import json
import time
import os
from pathlib import Path

# Add src to path
sys.path.append('src')

from scraper.funtrivia import FunTriviaScraper

async def test_incremental_save():
    """Test incremental saving with a small number of quizzes."""
    print("🧪 Testing incremental saving functionality...")
    print("⏳ This will scrape 1-2 quizzes and save questions immediately")
    
    # Check initial state
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    print(f"\n📂 Monitoring output directory: {output_dir.absolute()}")
    print(f"Initial files: {list(output_dir.glob('*.csv'))}")
    
    scraper = FunTriviaScraper('config/settings.json')
    
    try:
        await scraper.initialize()
        print("✅ Scraper initialized with incremental saving enabled")
        
        # Get categories
        categories = await scraper._get_categories()
        print(f"📂 Found {len(categories)} categories")
        
        # Process just one category with a few quizzes
        if categories:
            category = categories[0]
            print(f"🔍 Processing category: {category}")
            
            quiz_links = await scraper._get_quiz_links(category)
            print(f"📋 Found {len(quiz_links)} quizzes in category")
            
            # Test with just 2 quizzes
            test_quizzes = quiz_links[:2]
            total_saved = 0
            
            for i, quiz_link in enumerate(test_quizzes, 1):
                print(f"\n🚀 Processing quiz {i}/{len(test_quizzes)}: {quiz_link}")
                
                # Check files before processing
                csv_files_before = list(output_dir.glob('*.csv'))
                
                # Scrape the quiz (this should save questions immediately)
                quiz_questions = await scraper._scrape_quiz(quiz_link)
                
                # Check files after processing
                csv_files_after = list(output_dir.glob('*.csv'))
                
                if quiz_questions:
                    print(f"✅ Quiz {i} completed: {len(quiz_questions)} questions processed")
                    total_saved += len(quiz_questions)
                    
                    # Verify files were created/updated
                    if csv_files_after != csv_files_before:
                        print(f"📁 CSV files updated: {[f.name for f in csv_files_after]}")
                    
                    # Show file sizes
                    for csv_file in csv_files_after:
                        if csv_file.exists():
                            size = csv_file.stat().st_size
                            print(f"   {csv_file.name}: {size} bytes")
                else:
                    print(f"⚠️ Quiz {i} failed - no questions extracted")
                
                # Small delay between quizzes
                await asyncio.sleep(2)
        
        print(f"\n🎉 Test completed!")
        print(f"📊 Total questions saved: {total_saved}")
        print(f"📁 Final CSV files: {list(output_dir.glob('*.csv'))}")
        
        # Show final file contents summary
        for csv_file in output_dir.glob('*.csv'):
            if csv_file.exists():
                try:
                    with open(csv_file, 'r') as f:
                        lines = f.readlines()
                        print(f"   {csv_file.name}: {len(lines)} lines (including header)")
                except Exception as e:
                    print(f"   {csv_file.name}: Error reading file - {e}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(test_incremental_save()) 