#!/usr/bin/env python3
"""
Test script to verify quiz type detection and handling
"""

import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.scraper.funtrivia import FunTriviaScraper

async def test_quiz_types():
    """Test quiz type detection and filtering."""
    
    print("🔍 Testing Quiz Type Detection")
    
    # Load config
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    
    scraper = FunTriviaScraper('config/settings.json')
    
    try:
        await scraper.initialize()
        
        # Get multiple categories to test different quiz types
        categories = await scraper._get_categories()
        print(f"✅ Found {len(categories)} categories")
        
        quiz_types_found = {}
        quizzes_tested = 0
        max_quizzes_to_test = 10
        
        for category_url in categories[:5]:  # Test first 5 categories
            try:
                quiz_links = await scraper._get_quiz_links(category_url)
                print(f"📁 Category: {category_url.split('/')[-2]} - {len(quiz_links)} quizzes")
                
                for quiz_url in quiz_links[:3]:  # Test first 3 quizzes per category
                    if quizzes_tested >= max_quizzes_to_test:
                        break
                        
                    # Test quiz type detection
                    context = await scraper.browser.new_context()
                    page = await context.new_page()
                    
                    try:
                        await page.goto(quiz_url, timeout=45000)
                        await page.wait_for_load_state('networkidle', timeout=30000)
                        
                        quiz_type = await scraper._detect_quiz_type(page)
                        
                        if quiz_type not in quiz_types_found:
                            quiz_types_found[quiz_type] = []
                        quiz_types_found[quiz_type].append(quiz_url)
                        
                        print(f"  🎯 {quiz_type}: {quiz_url.split('/')[-1][:50]}...")
                        
                        # Test actual scraping for compatible types
                        if quiz_type in ['Multiple Choice', 'Photo Quiz']:
                            questions = await scraper._scrape_quiz(quiz_url)
                            if questions:
                                q = questions[0]
                                has_image = bool(q.get('media_path') or q.get('image_path'))
                                print(f"      ✅ Extracted {len(questions)} questions")
                                if has_image:
                                    print(f"      🖼️  Has image: {q.get('media_path', q.get('image_path', 'N/A'))}")
                            else:
                                print(f"      ❌ No questions extracted")
                        else:
                            print(f"      ⏭️  Skipped - incompatible type")
                        
                    except Exception as e:
                        print(f"      ❌ Error: {str(e)[:50]}...")
                    finally:
                        await context.close()
                    
                    quizzes_tested += 1
                    
                    if quizzes_tested >= max_quizzes_to_test:
                        break
                        
            except Exception as e:
                print(f"❌ Error with category {category_url}: {e}")
                continue
        
        # Summary
        print(f"\n" + "="*60)
        print(f"🎯 QUIZ TYPE DETECTION SUMMARY")
        print(f"="*60)
        print(f"Total quizzes tested: {quizzes_tested}")
        
        for quiz_type, urls in quiz_types_found.items():
            compatible = "✅ COMPATIBLE" if quiz_type in ['Multiple Choice', 'Photo Quiz'] else "❌ SKIP"
            print(f"{quiz_type}: {len(urls)} found {compatible}")
            
        print(f"\n📊 Coverage:")
        compatible_count = len(quiz_types_found.get('Multiple Choice', [])) + len(quiz_types_found.get('Photo Quiz', []))
        total_count = sum(len(urls) for urls in quiz_types_found.values())
        coverage = (compatible_count / total_count * 100) if total_count > 0 else 0
        print(f"Compatible quizzes: {compatible_count}/{total_count} ({coverage:.1f}%)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(test_quiz_types()) 