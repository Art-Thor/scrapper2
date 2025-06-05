#!/usr/bin/env python3
"""
Timing test for 20 questions
"""

import asyncio
import sys
import os
import json
import time
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.scraper.funtrivia import FunTriviaScraper

async def time_20_questions():
    """Time how long it takes to scrape exactly 20 questions."""
    
    print(f"🕒 Starting 20-question timing test at {datetime.now().strftime('%H:%M:%S')}")
    start_time = time.time()
    
    # Load config
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    
    scraper = FunTriviaScraper('config/settings.json')
    total_questions = 0
    quiz_count = 0
    
    try:
        await scraper.initialize()
        print(f"✅ Scraper initialized at {time.time() - start_time:.1f}s")
        
        # Get categories and quizzes
        categories = await scraper._get_categories()
        print(f"✅ Found {len(categories)} categories at {time.time() - start_time:.1f}s")
        
        if categories:
            # Try multiple categories to find one with enough quizzes
            quiz_links = []
            for category_url in categories[:5]:  # Try first 5 categories
                try:
                    links = await scraper._get_quiz_links(category_url)
                    if len(links) > 1:  # Found a category with multiple quizzes
                        quiz_links = links
                        print(f"✅ Using category with {len(quiz_links)} quizzes")
                        break
                except:
                    continue
            
            if not quiz_links:
                # Fallback to first category
                quiz_links = await scraper._get_quiz_links(categories[0])
            
            print(f"✅ Found {len(quiz_links)} quizzes at {time.time() - start_time:.1f}s")
            
            # Scrape quizzes until we have 20 questions
            for quiz_url in quiz_links:
                if total_questions >= 20:
                    break
                
                quiz_start = time.time()
                questions = await scraper._scrape_quiz(quiz_url)
                quiz_time = time.time() - quiz_start
                
                if questions:
                    quiz_count += 1
                    questions_this_quiz = len(questions)
                    total_questions += questions_this_quiz
                    
                    print(f"📋 Quiz {quiz_count}: {questions_this_quiz} questions in {quiz_time:.1f}s")
                    print(f"    Total so far: {total_questions} questions")
                    print(f"    Elapsed: {time.time() - start_time:.1f}s")
                    
                    if total_questions >= 20:
                        print(f"🎯 Target reached! Got {total_questions} questions")
                        break
        
        total_time = time.time() - start_time
        
        print(f"\n" + "="*50)
        print(f"⏱️  TIMING RESULTS")
        print(f"="*50)
        print(f"Total Questions: {total_questions}")
        print(f"Quizzes Scraped: {quiz_count}")
        print(f"Total Time: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
        print(f"Questions/Second: {total_questions/total_time:.2f}")
        print(f"Average per Quiz: {total_time/quiz_count:.1f}s")
        print(f"Questions per Quiz: {total_questions/quiz_count:.1f}")
        
        # Extrapolate for exactly 20 questions
        if total_questions > 20:
            estimated_time_20 = (total_time / total_questions) * 20
            print(f"\n🎯 Estimated time for exactly 20 questions: {estimated_time_20:.1f}s ({estimated_time_20/60:.1f} min)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()
        print(f"🏁 Test completed at {datetime.now().strftime('%H:%M:%S')}")

if __name__ == '__main__':
    asyncio.run(time_20_questions()) 