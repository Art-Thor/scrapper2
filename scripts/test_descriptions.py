#!/usr/bin/env python3
"""
Test script to verify description/explanation extraction and saving.
This will scrape one quiz and check if explanations are properly saved.
"""

import asyncio
import sys
import pandas as pd
from pathlib import Path

# Add src to path
sys.path.append('src')

from scraper.funtrivia import FunTriviaScraper

async def test_description_extraction():
    """Test description extraction with one quiz."""
    print("🔍 Testing description/explanation extraction...")
    
    scraper = FunTriviaScraper('config/settings.json')
    
    try:
        await scraper.initialize()
        print("✅ Scraper initialized")
        
        # Get one category and one quiz
        categories = await scraper._get_categories()
        if not categories:
            print("❌ No categories found")
            return
        
        category = categories[0]
        quiz_links = await scraper._get_quiz_links(category)
        if not quiz_links:
            print("❌ No quizzes found")
            return
        
        # Test with first quiz
        quiz_link = quiz_links[0]
        print(f"🎯 Testing quiz: {quiz_link}")
        
        # Clear any existing output files for clean test
        output_dir = Path("output")
        for csv_file in output_dir.glob("*.csv"):
            csv_file.unlink()
        
        # Scrape the quiz
        questions = await scraper._scrape_quiz(quiz_link)
        
        if questions:
            print(f"✅ Extracted {len(questions)} questions")
            
            # Check descriptions in the questions data
            descriptions_found = 0
            for i, q in enumerate(questions, 1):
                description = q.get('description', '')
                hint = q.get('hint', '')
                
                print(f"Question {i}:")
                print(f"  ID: {q.get('id', 'N/A')}")
                print(f"  Question: {q.get('question', '')[:80]}...")
                print(f"  Correct Answer: {q.get('correct_answer', 'N/A')}")
                print(f"  Description: {len(description)} chars - {'✅' if description else '❌'}")
                print(f"  Hint: {len(hint)} chars - {'✅' if hint else '❌'}")
                
                if description or hint:
                    descriptions_found += 1
                    print(f"  Preview: {(description or hint)[:100]}...")
                print()
            
            print(f"📊 Summary: {descriptions_found}/{len(questions)} questions have descriptions/hints")
            
            # Check saved CSV files
            print("\n📁 Checking saved CSV files...")
            csv_files = list(output_dir.glob("*.csv"))
            
            for csv_file in csv_files:
                print(f"\n📄 {csv_file.name}:")
                try:
                    df = pd.read_csv(csv_file)
                    print(f"  Rows: {len(df)}")
                    
                    # Check Description and Hint columns
                    desc_count = df['Description'].notna().sum() if 'Description' in df.columns else 0
                    hint_count = df['Hint'].notna().sum() if 'Hint' in df.columns else 0
                    desc_with_content = (df['Description'].str.len() > 0).sum() if 'Description' in df.columns else 0
                    hint_with_content = (df['Hint'].str.len() > 0).sum() if 'Hint' in df.columns else 0
                    
                    print(f"  Description column: {desc_with_content}/{len(df)} have content")
                    print(f"  Hint column: {hint_with_content}/{len(df)} have content")
                    
                    # Show sample descriptions
                    if 'Description' in df.columns and desc_with_content > 0:
                        sample_desc = df[df['Description'].str.len() > 0]['Description'].iloc[0]
                        print(f"  Sample description: {sample_desc[:100]}...")
                    
                except Exception as e:
                    print(f"  Error reading CSV: {e}")
            
        else:
            print("❌ No questions extracted")
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(test_description_extraction()) 