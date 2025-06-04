#!/usr/bin/env python3
"""
Simple test script
"""

import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.scraper.funtrivia import FunTriviaScraper
from src.utils.csv_handler import CSVHandler

async def test_specific_quiz():
    """Test extraction on a specific quiz URL that worked before."""
    
    # Use the URL that worked in our debug session
    quiz_url = "https://www.funtrivia.com/quiz/humanities/funtrivia-humanities-mix-vol-19-416258.html"
    
    print(f"🧪 Testing quiz: {quiz_url}")
    
    # Load config
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    
    scraper = FunTriviaScraper('config/settings.json')
    csv_handler = CSVHandler(config['storage']['output_dir'])
    
    try:
        await scraper.initialize()
        
        # Directly scrape this specific quiz
        questions = await scraper._scrape_quiz(quiz_url)
        
        if questions:
            print(f"✅ Extracted {len(questions)} questions")
            
            # Show details of first question
            if questions:
                q = questions[0]
                print(f"\n📋 First question details:")
                for key, value in q.items():
                    if isinstance(value, list):
                        print(f"  {key}: {value}")
                    else:
                        print(f"  {key}: {value}")
                
                # Format for CSV
                formatted_questions = []
                for q in questions[:3]:  # First 3
                    formatted = {
                        'Key': q.get('id', ''),
                        'Domain': q.get('domain', 'Culture'),
                        'Topic': q.get('topic', 'General'),
                        'Difficulty': q.get('difficulty', 'Normal'),
                        'Question': q.get('question', ''),
                        'Option1': '',
                        'Option2': '',
                        'Option3': '',
                        'Option4': '',
                        'CorrectAnswer': q.get('correct_answer', ''),
                        'Hint': q.get('hint', ''),
                        'ImagePath': '',
                        'AudioPath': ''
                    }
                    
                    options = q.get('options', [])
                    for i, option in enumerate(options[:4], 1):
                        formatted[f'Option{i}'] = option.strip()
                    
                    formatted_questions.append(formatted)
                
                # Save to CSV
                csv_file = config['storage']['csv_files']['multiple_choice']
                count = csv_handler.append_to_csv(formatted_questions, csv_file, 'multiple_choice')
                
                print(f"\n💾 Saved {count} questions to output/{csv_file}")
        else:
            print("❌ No questions extracted")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(test_specific_quiz()) 