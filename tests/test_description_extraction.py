#!/usr/bin/env python3
"""
Test script for description extraction functionality.

This script tests the enhanced scraper's ability to extract question descriptions
from FunTrivia quiz results pages.
"""

import asyncio
import sys
import os
import json
import logging

# Add src to path for imports
sys.path.append('src')

from scraper.funtrivia import FunTriviaScraper

async def test_description_extraction():
    """Test the description extraction functionality."""
    print("🧪 Testing Description Extraction Functionality")
    print("=" * 60)
    
    # Load configuration
    try:
        with open('config/settings.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ Configuration file not found!")
        return False
    
    # Initialize scraper
    scraper = FunTriviaScraper('config/settings.json')
    
    try:
        await scraper.initialize()
        print("✅ Scraper initialized successfully")
        
        # Test with a specific quiz (you can modify this URL)
        test_quiz_url = "https://www.funtrivia.com/quiz/television/tv-trivia-mixed-bag-418931.html"
        
        print(f"🔍 Testing with quiz: {test_quiz_url}")
        print("📝 Extracting questions and descriptions...")
        
        # Scrape the quiz
        questions = await scraper._scrape_quiz(test_quiz_url)
        
        if questions:
            print(f"✅ Successfully extracted {len(questions)} questions")
            
            # Check if descriptions were extracted
            questions_with_descriptions = [q for q in questions if q.get('description')]
            print(f"📋 Questions with descriptions: {len(questions_with_descriptions)}")
            
            # Display sample results
            print("\n" + "=" * 60)
            print("SAMPLE RESULTS")
            print("=" * 60)
            
            for i, question in enumerate(questions[:3], 1):  # Show first 3 questions
                print(f"\n🔹 Question {i}:")
                print(f"   Text: {question.get('question', 'N/A')[:80]}...")
                print(f"   Type: {question.get('type', 'N/A')}")
                print(f"   Options: {len(question.get('options', []))}")
                print(f"   Description: {question.get('description', 'No description found')[:100]}...")
                
                if question.get('description'):
                    print("   ✅ Description extracted successfully")
                else:
                    print("   ⚠️ No description found")
            
            # Summary
            success_rate = (len(questions_with_descriptions) / len(questions)) * 100
            print(f"\n📊 Success Rate: {success_rate:.1f}% of questions have descriptions")
            
            if success_rate > 0:
                print("✅ Description extraction is working!")
                return True
            else:
                print("❌ No descriptions were extracted")
                return False
                
        else:
            print("❌ No questions were extracted")
            return False
            
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        logging.getLogger(__name__).error(f"Test failed: {e}", exc_info=True)
        return False
        
    finally:
        await scraper.close()
        print("\n🔄 Scraper closed")

async def test_csv_structure():
    """Test that the CSV structure includes the Description field."""
    print("\n🧪 Testing CSV Structure")
    print("=" * 40)
    
    sys.path.append('src')
    from utils.csv_handler import CSVHandler
    
    csv_handler = CSVHandler()
    
    # Test all question types
    for question_type in ['multiple_choice', 'true_false', 'sound']:
        columns = csv_handler.get_csv_columns(question_type)
        if 'Description' in columns:
            print(f"✅ {question_type}: Description field present")
        else:
            print(f"❌ {question_type}: Description field missing")
    
    print("\nColumn structure for multiple_choice:")
    for i, col in enumerate(csv_handler.get_csv_columns('multiple_choice'), 1):
        print(f"  {i:2d}. {col}")

async def main():
    """Run all tests."""
    print("🚀 Starting Description Extraction Tests")
    print("=" * 60)
    
    # Set up basic logging
    logging.basicConfig(
        level=logging.WARNING,  # Reduce noise during testing
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test CSV structure first
    await test_csv_structure()
    
    # Test description extraction
    success = await test_description_extraction()
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    if success:
        print("✅ All tests passed! Description extraction is working.")
        print("\n📋 Next steps:")
        print("1. Run the main scraper with: python src/main.py --max-questions 5")
        print("2. Check the CSV files for the new Description column")
        print("3. Verify that descriptions are being populated")
    else:
        print("❌ Some tests failed. Check the error messages above.")
        print("\n🔧 Troubleshooting:")
        print("1. Ensure the scraper can access FunTrivia")
        print("2. Check that the quiz URL is valid")
        print("3. Verify browser/Playwright setup")

if __name__ == '__main__':
    asyncio.run(main()) 