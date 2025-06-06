#!/usr/bin/env python3
"""
Optimization script to:
1. Test correct answer extraction with real options  
2. Create a more efficient single-pass extraction method
3. Eliminate duplication in question processing
"""

import asyncio
import sys
sys.path.append('.')

from playwright.async_api import async_playwright
from src.scraper.funtrivia import FunTriviaScraper

async def test_optimized_extraction():
    """Test extraction with real quiz data to verify fixes."""
    
    print("🧪 Testing optimized extraction pipeline...")
    
    async with async_playwright() as p:
        # Initialize scraper 
        scraper = FunTriviaScraper(speed_profile='fast')
        await scraper.initialize()
        
        try:
            # Test with a single quiz to verify no duplication
            quiz_url = "https://www.funtrivia.com/quiz/religion/religious-services-300285.html"
            print(f"📄 Testing with: {quiz_url}")
            
            questions = await scraper._scrape_quiz(quiz_url)
            
            print(f"\n📊 RESULTS:")
            print(f"Questions extracted: {len(questions)}")
            
            # Analyze correct answers
            for i, q in enumerate(questions[:5]):  # Check first 5
                question_text = q.get('question', '')[:80] + "..."
                correct_answer = q.get('correct_answer', 'N/A')
                options = q.get('options', [])
                description_len = len(q.get('description', ''))
                
                print(f"\nQ{i+1}: {question_text}")
                print(f"Options: {options}")
                print(f"Correct Answer: {correct_answer}")
                print(f"Description: {description_len} chars")
                
                # Check if correct answer matches any option
                if correct_answer in options:
                    print("✅ Correct answer matches option")
                else:
                    print("❌ Correct answer doesn't match any option!")
                    
                    # Try to find partial matches
                    for opt in options:
                        if (opt.lower() in correct_answer.lower() or 
                            correct_answer.lower() in opt.lower()):
                            print(f"🔍 Partial match found: '{opt}' <-> '{correct_answer}'")
                            break
                    else:
                        print("🚨 No matches found - this will default to first option!")
            
        except Exception as e:
            print(f"❌ Error during test: {e}")
        
        finally:
            await scraper.close()

if __name__ == "__main__":
    print("🔧 Correct Answer Extraction Optimizer")
    print("=" * 50)
    
    # Run the test
    asyncio.run(test_optimized_extraction())
    
    print("\n💡 Based on results:")
    print("1. If correct answers don't match options -> improve extraction")
    print("2. If extraction is slow -> optimize processing pipeline") 
    print("3. If descriptions missing -> check regex patterns")
    print("\n✅ Test complete!") 