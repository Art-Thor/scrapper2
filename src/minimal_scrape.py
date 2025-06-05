#!/usr/bin/env python3
"""
Script to scrape questions with production settings.
"""

import asyncio
import sys
import json
import pandas as pd # type: ignore
from pathlib import Path
import os
import random

# Add the parent directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.scraper.funtrivia import FunTriviaScraper
from src.utils.csv_handler import CSVHandler

async def quick_scrape(max_questions=100):
    """Scrape questions with production settings."""
    print(f"🔄 Scraping {max_questions} questions with production settings...")
    
    # Load config
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    
    # Update config with production settings
    config['scraping'] = {
        'concurrency': 2,
        'min_delay': 3,
        'max_delay': 8,
        'max_retries': 3,
        'timeout': 30
    }
    
    scraper = FunTriviaScraper('config/settings.json')
    csv_handler = CSVHandler(config['storage']['output_dir'])
    
    try:
        await scraper.initialize()
        
        questions_collected = 0
        categories = await scraper._get_categories()
        
        if not categories:
            print("❌ No categories found")
            return
            
        while questions_collected < max_questions and categories:
            # Randomly select a category to distribute the load
            category_url = random.choice(categories)
            quiz_links = await scraper._get_quiz_links(category_url)
            
            if quiz_links:
                # Randomly select a quiz
                quiz_url = random.choice(quiz_links)
                questions = await scraper._scrape_quiz(quiz_url)
                
                if questions:
                    # Take only what we need
                    remaining = max_questions - questions_collected
                    questions = questions[:remaining]
                    questions_collected += len(questions)
                    
                    print(f"✅ Scraped {len(questions)} questions from {quiz_url}")
                    
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
                            formatted.update({
                                'Option3': '',
                                'Option4': '',
                                'ImagePath': q.get('media_path', '')
                            })
                        elif question_type == 'true_false':
                            pass  # Already has Option1, Option2
                        elif question_type == 'sound':
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
                    
                    print(f"💾 Progress: {questions_collected}/{max_questions} questions collected")
                    
                    # Add delay between quizzes
                    await asyncio.sleep(random.uniform(config['scraping']['min_delay'], 
                                                     config['scraping']['max_delay']))
                    
            if questions_collected >= max_questions:
                break
                
        print(f"\n✨ Scraping completed! Total questions collected: {questions_collected}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(quick_scrape(100)) 