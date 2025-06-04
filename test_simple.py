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
                    # Get question type to determine correct fields
                    question_type = q.get('type', 'multiple_choice')
                    
                    # Base structure common to all question types
                    formatted = {
                        'Key': q.get('id', ''),
                        'Domain': q.get('domain', 'Culture'),
                        'Topic': q.get('topic', 'General'),
                        'Difficulty': q.get('difficulty', 'Normal'),
                        'Question': q.get('question', ''),
                        'Option1': '',
                        'Option2': '',
                        'CorrectAnswer': q.get('correct_answer', ''),
                        'Hint': q.get('hint', ''),
                        'Description': q.get('description', '')
                    }

                    # Add question type-specific fields
                    if question_type == 'multiple_choice':
                        # Multiple choice has 4 options and ImagePath
                        formatted.update({
                            'Option3': '',
                            'Option4': '',
                            'ImagePath': q.get('media_path', '')
                        })
                    elif question_type == 'true_false':
                        # True/false only has 2 options, no media path
                        pass  # Already has Option1, Option2
                    elif question_type == 'sound':
                        # Sound has 4 options and AudioPath
                        formatted.update({
                            'Option3': '',
                            'Option4': '',
                            'AudioPath': q.get('media_path', '')
                        })
                    
                    # Fill in options based on question type
                    options = q.get('options', [])
                    max_options = 4 if question_type in ['multiple_choice', 'sound'] else 2
                    for i, option in enumerate(options[:max_options], 1):
                        formatted[f'Option{i}'] = option.strip()
                    
                    formatted_questions.append(formatted)
                
                # Save to appropriate CSV based on question type
                questions_by_type = {
                    'multiple_choice': [],
                    'true_false': [],
                    'sound': []
                }
                
                for formatted_q in formatted_questions:
                    q_type = next((q.get('type', 'multiple_choice') for q in questions 
                                 if q.get('id') == formatted_q['Key']), 'multiple_choice')
                    questions_by_type[q_type].append(formatted_q)
                
                total_saved = 0
                for q_type, type_questions in questions_by_type.items():
                    if type_questions:
                        csv_file = config['storage']['csv_files'][q_type]
                        count = csv_handler.append_to_csv(type_questions, csv_file, q_type)
                        total_saved += count
                        print(f"💾 Saved {count} {q_type} questions to output/{csv_file}")
                
                print(f"\n💾 Total saved: {total_saved} questions")
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