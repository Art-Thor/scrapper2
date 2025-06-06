#!/usr/bin/env python3
"""
Quick test to verify enhanced description extraction logic.
"""

import asyncio
import logging
from src.scraper.funtrivia import FunTriviaScraper

async def test_description_extraction():
    """Test the enhanced description extraction with a single quiz."""
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    print("🧪 Testing Enhanced Description Extraction")
    print("=" * 50)
    
    # Initialize scraper
    scraper = FunTriviaScraper(speed_profile="fast")
    await scraper.initialize()
    
    try:
        # Test with a known Photo Quiz that should have descriptions
        test_urls = [
            "https://www.funtrivia.com/quiz/geography/great-lakes-416213.html",
            "https://www.funtrivia.com/quiz/animals/fact-or-fiction-leopards-and-cheetahs-418840.html"
        ]
        
        for i, quiz_url in enumerate(test_urls, 1):
            print(f"\n🎯 Test {i}: {quiz_url}")
            
            try:
                # Scrape the quiz
                questions = await scraper._scrape_quiz(quiz_url)
                
                if questions:
                    print(f"   ✅ Extracted {len(questions)} questions")
                    
                    # Check descriptions
                    questions_with_descriptions = [q for q in questions if q.get('description') or q.get('hint')]
                    description_rate = (len(questions_with_descriptions) / len(questions)) * 100
                    
                    print(f"   📋 Questions with descriptions: {len(questions_with_descriptions)}/{len(questions)} ({description_rate:.1f}%)")
                    
                    # Show sample descriptions
                    if questions_with_descriptions:
                        print(f"   📝 Sample descriptions:")
                        for j, q in enumerate(questions_with_descriptions[:3], 1):
                            desc = q.get('description') or q.get('hint', '')
                            if desc:
                                preview = desc[:100] + "..." if len(desc) > 100 else desc
                                print(f"      {j}. {preview}")
                        
                        print(f"   🎉 SUCCESS: Description extraction is working!")
                    else:
                        print(f"   ⚠️ No descriptions found")
                        
                else:
                    print(f"   ❌ No questions extracted")
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                
            # Small delay between tests
            await asyncio.sleep(2)
            
    finally:
        await scraper.close()
        print(f"\n✅ Test completed")

if __name__ == "__main__":
    asyncio.run(test_description_extraction()) 