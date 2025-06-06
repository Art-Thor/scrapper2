#!/usr/bin/env python3
"""
Test script to verify that correct answer extraction is working properly.
This tests the specific issue found with the Max Brooks "World War Z" question.
"""

import re
from typing import List, Dict, Any, Optional

def _split_page_text_by_questions(page_text: str) -> Dict[str, str]:
    """Split the page text into sections for each question."""
    try:
        sections = {}
        
        # Look for question number patterns like "Question 1", "1.", etc.
        question_pattern = r'(\d+)\.\s+'
        
        matches = list(re.finditer(question_pattern, page_text, re.MULTILINE | re.IGNORECASE))
        print(f"Found {len(matches)} pattern matches")
        for match in matches:
            print(f"Match: {match.group()} at position {match.start()}-{match.end()}")
        
        for i, match in enumerate(matches):
            # Get question number from the capture group
            question_num = match.group(1)
            if not question_num:
                continue
            
            # Get the start position of this question's content
            start_pos = match.start()
            
            # Get the end position (start of next question or end of text)
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(page_text)
            
            # Extract the section text for this question
            section_text = page_text[start_pos:end_pos].strip()
            sections[question_num] = section_text
            
        print(f"Split page text into {len(sections)} question sections")
        return sections
        
    except Exception as e:
        print(f"Error splitting page text by questions: {e}")
        return {}

def _extract_correct_answer_from_page_text(page_text: str, question_num: str, question: Dict[str, Any]) -> Optional[str]:
    """Extract correct answer for a specific question from the full page text."""
    try:
        # Get question options to validate against
        question_options = question.get('options', [])
        
        # Split page text into sections by question
        question_sections = _split_page_text_by_questions(page_text)
        
        # Look for correct answer in the specific question's section
        if question_num in question_sections:
            section_text = question_sections[question_num]
            print(f"\n=== SECTION TEXT FOR Q{question_num} ===")
            print(section_text[:500] + "..." if len(section_text) > 500 else section_text)
            print("=" * 50)
            
            # Enhanced patterns to find correct answers
            patterns = [
                r'The correct answer was\s+([^.\n\r]+)',
                r'Correct answer was\s+([^.\n\r]+)', 
                r'correct answer:\s*([^.\n\r]+)',
                r'The correct answer is\s+([^.\n\r]+)',
                r'Answer:\s*([^.\n\r]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, section_text, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    answer_text = match.strip()
                    print(f"Found answer candidate: '{answer_text}'")
                    
                    # Try to match with actual question options
                    for option in question_options:
                        option_clean = option.strip()
                        # Exact match
                        if option_clean.lower() == answer_text.lower():
                            print(f"✅ Found exact correct answer for Q{question_num}: {option_clean}")
                            return option_clean
                        # Partial match (answer contains option or vice versa)
                        elif (option_clean.lower() in answer_text.lower() or 
                              answer_text.lower() in option_clean.lower()):
                            print(f"✅ Found partial correct answer for Q{question_num}: {option_clean}")
                            return option_clean
                    
                    # If no option match, return the raw answer (might be formatted differently)
                    if answer_text and len(answer_text) > 1:
                        print(f"⚠️ Found raw correct answer for Q{question_num}: {answer_text}")
                        return answer_text
        
        print(f"❌ No correct answer found for Q{question_num}")
        return None
        
    except Exception as e:
        print(f"❌ Error extracting correct answer for Q{question_num}: {e}")
        return None

def test_world_war_z_question():
    """Test the specific World War Z question that was having issues."""
    
    # Sample text based on the actual FunTrivia results page structure
    sample_page_text = """
    3. Regarding the Max Brooks book titled "World War Z", what does the 'Z' stand for?
    
    ❌ Your Answer: [No Answer]
    
    The correct answer was Zombie
    
    Written after "The Zombie Survival Guide", Max Brooks created the "Oral History of the Zombie War" in releasing "World War Z" in 2006, chronicling the rise of a zombie outbreak through its stages and following the international efforts to abate it as told through first-hand accounts.
    
    The novel was a major success, becoming a bestseller and continuing a rising trend in zombie media at the time. The book was adapted into a Brad Pitt film in 2013 and a video game in 2019. Max Brooks, interestingly, is the son of famous comedic filmmaker Mel Brooks.
    
    Question by player kyleisalive
    
    91% of players have answered correctly.
    
    4. Next question here...
    """
    
    # Create the question data structure
    question = {
        'options': ['Zelda', 'Zebra', 'Zombie', 'Zaire'],
        'questionNumber': '3'
    }
    
    print("🧪 Testing World War Z question correct answer extraction")
    print("=" * 60)
    print(f"Question options: {question['options']}")
    print(f"Expected correct answer: Zombie")
    print("=" * 60)
    
    # Test the extraction
    result = _extract_correct_answer_from_page_text(sample_page_text, "3", question)
    
    print(f"\n🎯 RESULT: {result}")
    
    if result == "Zombie":
        print("✅ SUCCESS: Correctly extracted 'Zombie' as the answer!")
        return True
    else:
        print(f"❌ FAILED: Expected 'Zombie' but got '{result}'")
        return False

def test_multiple_questions():
    """Test extraction with multiple questions to ensure proper separation."""
    
    sample_page_text = """
    1. What is the capital of France?
    Your Answer: Paris
    The correct answer was Paris
    Paris is the capital and largest city of France.
    
    2. What is 2 + 2?
    Your Answer: [No Answer]
    The correct answer was Four
    This is basic arithmetic.
    
    3. Regarding the Max Brooks book titled "World War Z", what does the 'Z' stand for?
    Your Answer: [No Answer]
    The correct answer was Zombie
    Written after "The Zombie Survival Guide", Max Brooks created the "Oral History of the Zombie War"...
    
    4. What color is the sky?
    Your Answer: Blue
    The correct answer was Blue
    The sky appears blue due to light scattering.
    """
    
    questions = [
        {'options': ['London', 'Paris', 'Berlin', 'Madrid'], 'questionNumber': '1'},
        {'options': ['Three', 'Four', 'Five', 'Six'], 'questionNumber': '2'},
        {'options': ['Zelda', 'Zebra', 'Zombie', 'Zaire'], 'questionNumber': '3'},
        {'options': ['Red', 'Green', 'Blue', 'Yellow'], 'questionNumber': '4'}
    ]
    
    expected_answers = ['Paris', 'Four', 'Zombie', 'Blue']
    
    print("\n🧪 Testing multiple questions extraction")
    print("=" * 60)
    
    all_passed = True
    for i, (question, expected) in enumerate(zip(questions, expected_answers)):
        question_num = str(i + 1)
        result = _extract_correct_answer_from_page_text(sample_page_text, question_num, question)
        
        print(f"\nQ{question_num}: Expected '{expected}', Got '{result}'")
        if result == expected:
            print(f"✅ Q{question_num} PASSED")
        else:
            print(f"❌ Q{question_num} FAILED")
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    print("🔧 Testing Correct Answer Extraction Fix")
    print("=" * 60)
    
    # Test the specific World War Z issue
    test1_passed = test_world_war_z_question()
    
    # Test multiple questions 
    test2_passed = test_multiple_questions()
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    if test1_passed and test2_passed:
        print("🎉 ALL TESTS PASSED! The correct answer extraction fix is working!")
        print("✅ Individual question targeting works correctly")
        print("✅ Multiple question separation works correctly")
        print("✅ Option matching works correctly")
    else:
        print("❌ SOME TESTS FAILED - Need to debug further")
        if not test1_passed:
            print("  - World War Z test failed")
        if not test2_passed:
            print("  - Multiple questions test failed")
    
    print("\n💡 Next step: Test with actual scraper to verify CSV output") 