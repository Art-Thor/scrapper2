#!/usr/bin/env python3
"""
Minimal script to scrape just a few questions and save them immediately.
"""

import asyncio
import sys
import json
import pandas as pd # type: ignore
from pathlib import Path

# Remove sys.path.append('src') and update imports to absolute
from src.scraper.funtrivia import FunTriviaScraper
from src.utils.csv_handler import CSVHandler

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
                    
                    print(f"💾 Saved {count} questions to output/{csv_file}")
                    
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