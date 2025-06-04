#!/usr/bin/env python3
"""
Minimal script to scrape just a few questions and save them immediately.
"""

import asyncio
import sys
import json
import pandas as pd
from pathlib import Path

# Add src to path
sys.path.append('src')

from scraper.funtrivia import FunTriviaScraper
from utils.csv_handler import CSVHandler

async def quick_scrape():
    """Scrape 3 questions and save immediately."""
    print("🔄 Quick scraping 3 questions...")
    
    # Load config
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    
    scraper = FunTriviaScraper('config/settings.json')
    csv_handler = CSVHandler(config['storage']['output_dir'])
    
    try:
        await scraper.initialize()
        
        # Get just one quiz worth of questions
        categories = await scraper._get_categories()
        if categories:
            category_url = categories[0]  # Just first category
            quiz_links = await scraper._get_quiz_links(category_url)
            if quiz_links:
                quiz_url = quiz_links[0]  # Just first quiz
                questions = await scraper._scrape_quiz(quiz_url)
                
                if questions:
                    # Take only first 3 questions
                    questions = questions[:3]
                    
                    print(f"✅ Scraped {len(questions)} questions")
                    
                    # Format for CSV
                    formatted_questions = []
                    for q in questions:
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
                    
                    print(f"💾 Total saved: {total_saved} questions")
                    
                    # Show first question as example
                    if formatted_questions:
                        q = formatted_questions[0]
                        print(f"\n📋 Sample question:")
                        print(f"   ID: {q['Key']}")
                        print(f"   Question: {q['Question'][:80]}...")
                        print(f"   Options: {q['Option1']}, {q['Option2']}")
                        print(f"   Answer: {q['CorrectAnswer']}")
                else:
                    print("❌ No questions found")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(quick_scrape()) 