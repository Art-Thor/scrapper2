#!/usr/bin/env python3
"""
Quick test to verify section splitting and answer matching fixes.
Tests the logic without running full browser scraping.
"""

import sys
sys.path.append('.')

from src.scraper.funtrivia import FunTriviaScraper

def test_section_splitting():
    """Test the improved section splitting logic."""
    
    print("🧪 Testing section splitting and answer matching...")
    
    # Sample page text with multiple questions (simulating real FunTrivia results)
    sample_text = """
1. In the Muslim faith, what is al-Jumuah?
The correct answer was Friday prayer
Friday prayer is the congregational prayer held every Friday.

2. In the Lutheran Church, the Matins service contains prayers, hymns and readings from the Bible. What is displayed on the board at the front of the church?
The correct answer was A Psalm read at the beginning of the service
A Psalm is typically displayed to guide the congregation.

3. In Buddhism, practitioners will take part in a 'puja.' This may include lighting candles, offering flowers to Buddha, and what other activity?
The correct answer was Chanting
Chanting is a meditative practice in Buddhist worship.
"""
    
    # Test sample questions
    test_questions = [
        {
            'questionNumber': '1',
            'question': 'In the Muslim faith, what is al-Jumuah?',
            'options': ['The naming of a child', 'Friday prayer', 'Prayer for the sick', 'Prayer before meals']
        },
        {
            'questionNumber': '2', 
            'question': 'In the Lutheran Church, the Matins service contains prayers, hymns and readings from the Bible. What is displayed on the board at the front of the church?',
            'options': ['A Psalm read at the beginning of the service', 'The sequence of hymns listed on a board at the front of the church', 'The announcements of upcoming church events', 'A request for the congregants to sing more loudly']
        },
        {
            'questionNumber': '3',
            'question': 'In Buddhism, practitioners will take part in a \'puja.\' This may include lighting candles, offering flowers to Buddha, and what other activity?',
            'options': ['Writing their names on a register', 'Turning to face the back wall, as a sign of rejecting evil', 'Playing a trumpet for good luck', 'Chanting']
        }
    ]
    
    # Initialize scraper (no browser needed for this test)
    scraper = FunTriviaScraper()
    
    # Test section splitting
    sections = scraper._split_page_text_by_questions(sample_text)
    print(f"📊 Split into {len(sections)} sections")
    
    # Test answer extraction for each question
    for question in test_questions:
        q_num = question['questionNumber']
        options = question['options']
        
        print(f"\n🔍 Testing Question {q_num}:")
        print(f"Options: {options}")
        
        # Extract answer from text
        extracted_answer = scraper._extract_correct_answer_from_page_text(sample_text, q_num, question)
        print(f"Extracted Answer: '{extracted_answer}'")
        
        # Check if answer matches any option
        if extracted_answer in options:
            print(f"✅ PERFECT MATCH: '{extracted_answer}' found in options")
        else:
            print(f"❌ NO EXACT MATCH for '{extracted_answer}'")
            
            # Try partial matching
            for opt in options:
                if (opt.lower().strip() in extracted_answer.lower().strip() or
                    extracted_answer.lower().strip() in opt.lower().strip()):
                    print(f"🔍 Partial match: '{opt}' <-> '{extracted_answer}'")
                    break
            else:
                print("🚨 NO MATCHES FOUND - will default to first option")
    
    print(f"\n📋 Section Contents:")
    for q_num, section in sections.items():
        print(f"\nQ{q_num} section ({len(section)} chars):")
        print(f"'{section[:150]}{'...' if len(section) > 150 else ''}'")

if __name__ == "__main__":
    print("⚡ Quick Section Splitting Test")
    print("=" * 40)
    test_section_splitting()
    print("\n✅ Quick test complete!") 