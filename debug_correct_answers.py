#!/usr/bin/env python3
"""
Debug script to examine correct answer extraction issues.
This helps understand why the scraper is getting wrong answers.
"""

import re
from typing import Dict, List, Any, Optional
import asyncio
from playwright.async_api import async_playwright

class CorrectAnswerDebugger:
    def __init__(self):
        self.patterns = [
            r'The correct answer was\s+([^.\n\r]+)',
            r'Correct answer was\s+([^.\n\r]+)', 
            r'correct answer:\s*([^.\n\r]+)',
            r'The correct answer is\s+([^.\n\r]+)',
            r'Answer:\s*([^.\n\r]+)',
        ]
    
    def _split_page_text_by_questions(self, page_text: str) -> Dict[str, str]:
        """Split the page text into sections for each question."""
        try:
            sections = {}
            
            # Look for question number patterns like "Question 1", "1.", etc.
            question_pattern = r'(\d+)\.\s+'
            
            matches = list(re.finditer(question_pattern, page_text, re.MULTILINE | re.IGNORECASE))
            
            print(f"Found {len(matches)} question patterns")
            for match in matches:
                print(f"  Match: '{match.group()}' at position {match.start()}")
            
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
                print(f"Question {question_num} section: {len(section_text)} characters")
                
            return sections
            
        except Exception as e:
            print(f"Error splitting page text by questions: {e}")
            return {}
    
    def debug_extract_correct_answer(self, page_text: str, question_num: str, question_options: List[str]) -> Optional[str]:
        """Debug version of correct answer extraction."""
        try:
            print(f"\n🔍 DEBUGGING CORRECT ANSWER EXTRACTION FOR Q{question_num}")
            print("=" * 60)
            print(f"Question options: {question_options}")
            
            # Split page text into sections by question
            question_sections = self._split_page_text_by_questions(page_text)
            
            # Look for correct answer in the specific question's section
            if question_num in question_sections:
                section_text = question_sections[question_num]
                
                print(f"\n📄 SECTION TEXT FOR Q{question_num}:")
                print("-" * 40)
                print(section_text[:500] + "..." if len(section_text) > 500 else section_text)
                print("-" * 40)
                
                # Try each pattern
                for i, pattern in enumerate(self.patterns):
                    print(f"\n🔍 Trying pattern {i+1}: {pattern}")
                    
                    matches = re.findall(pattern, section_text, re.IGNORECASE | re.DOTALL)
                    print(f"Found {len(matches)} matches: {matches}")
                    
                    for match in matches:
                        answer_text = match.strip()
                        print(f"  Candidate answer: '{answer_text}'")
                        
                        # Try to match with actual question options
                        for option in question_options:
                            option_clean = option.strip()
                            # Exact match
                            if option_clean.lower() == answer_text.lower():
                                print(f"  ✅ EXACT MATCH: {option_clean}")
                                return option_clean
                            # Partial match
                            elif (option_clean.lower() in answer_text.lower() or 
                                  answer_text.lower() in option_clean.lower()):
                                print(f"  ✅ PARTIAL MATCH: {option_clean}")
                                return option_clean
                        
                        print(f"  ❌ No option match found for '{answer_text}'")
                
                print(f"\n❌ No patterns matched in section for Q{question_num}")
            else:
                print(f"❌ No section found for Q{question_num}")
                print(f"Available sections: {list(question_sections.keys())}")
            
            return None
            
        except Exception as e:
            print(f"❌ Error extracting correct answer for Q{question_num}: {e}")
            return None

async def debug_real_page():
    """Debug with actual FunTrivia page."""
    
    print("🚀 Starting real page debug...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Show browser for debugging
        page = await browser.new_page()
        
        try:
            # Navigate to a sample FunTrivia quiz (you can change this URL)
            quiz_url = "https://www.funtrivia.com/quiz/religion/religious-services-300285.html"
            print(f"📄 Navigating to: {quiz_url}")
            
            await page.goto(quiz_url)
            await page.wait_for_load_state('networkidle')
            
            # Click start quiz
            start_button = await page.query_selector('input[type="submit"][value*="Start Quiz"]')
            if start_button:
                await start_button.click()
                await page.wait_for_load_state('networkidle')
            
            # Extract questions first
            questions = []
            question_elements = await page.query_selector_all('.question')
            if not question_elements:
                question_elements = await page.query_selector_all('[class*="question"]')
            
            print(f"Found {len(question_elements)} question elements")
            
            # For simplicity, let's just answer a few questions incorrectly to get to results
            radio_buttons = await page.query_selector_all('input[type="radio"]')
            if radio_buttons:
                print(f"Found {len(radio_buttons)} radio buttons")
                # Click the first option for each question (likely wrong)
                for i in range(0, min(len(radio_buttons), 8), 4):  # Every 4th (first option of each question)
                    try:
                        await radio_buttons[i].click()
                        await asyncio.sleep(0.1)
                    except:
                        pass
            
            # Submit quiz
            submit_button = await page.query_selector('input[type="submit"][value*="Submit"]')
            if submit_button:
                print("📤 Submitting quiz...")
                await submit_button.click()
                await page.wait_for_load_state('networkidle')
                await asyncio.sleep(2)  # Wait for results to load
            
            # Now extract the page text and debug
            page_text = await page.inner_text("body")
            print(f"📄 Page text length: {len(page_text)} characters")
            
            # Save page text for inspection
            with open("debug_page_text.txt", "w", encoding="utf-8") as f:
                f.write(page_text)
            print("💾 Saved page text to debug_page_text.txt")
            
            # Try to debug a specific question
            debugger = CorrectAnswerDebugger()
            
            # Test with the known problematic question
            test_options = ["Prayer before meals", "The naming of a child", "Friday prayer", "Prayer for the sick"]
            result = debugger.debug_extract_correct_answer(page_text, "8", test_options)
            
            print(f"\n🎯 FINAL RESULT: {result}")
            
            input("Press Enter to close browser...")
            
        except Exception as e:
            print(f"❌ Error in debug: {e}")
        
        finally:
            await browser.close()

def debug_sample_text():
    """Debug with sample text from the screenshot."""
    
    sample_text = """
    7. In the Roman Catholic Church, the Easter Vigil is held late in the day on Holy Saturday. The rubrics of the Mass call for the faithful to do something they have not done at any services since the beginning of Lent. What is this?
    
    ❌ Your Answer: [No Answer]
    
    The correct answer was Use the word "Alleluia"
    
    "Alleluia" is a term considered appropriate to celebrations of the risen Christ, and therefore not said during Lent. The Easter Vigil customarily lasts about three hours. In many areas, it is held so as to run from late Saturday night until early Easter Sunday morning. It is also the service at which new converts are received into the church, through Baptism and/or Confirmation.
    
    55% of players have answered correctly.
    
    8. In the Muslim faith, what is al-Jumuah?
    
    ❌ Your Answer: [No Answer]
    
    The correct answer was Friday prayer
    
    This is held at a mosque (masjid). Al-Jumuah is observed at noon.
    
    44% of players have answered correctly.
    
    9. In the Hindu faith, during what time of day is the Nitya Puja service performed?
    
    ❌ Your Answer: [No Answer]
    
    The correct answer was Morning
    
    The puja may be accompanied by Kirtan or Dhun music. One may also sit on a mat, called an asan.
    """
    
    debugger = CorrectAnswerDebugger()
    
    # Test question 8 (the problematic one)
    test_options = ["Prayer before meals", "The naming of a child", "Friday prayer", "Prayer for the sick"]
    result = debugger.debug_extract_correct_answer(sample_text, "8", test_options)
    
    print(f"\n🎯 RESULT FOR Q8: {result}")
    print(f"Expected: Friday prayer")
    print(f"Match: {'✅' if result == 'Friday prayer' else '❌'}")

if __name__ == "__main__":
    print("🔧 Correct Answer Extraction Debugger")
    print("=" * 50)
    
    # First test with sample text
    print("\n1️⃣ Testing with sample text from screenshot:")
    debug_sample_text()
    
    # Ask if user wants to test with real page
    print("\n2️⃣ Would you like to test with a real FunTrivia page?")
    choice = input("Type 'y' for yes, anything else to skip: ").lower().strip()
    
    if choice == 'y':
        asyncio.run(debug_real_page())
    else:
        print("Skipping real page test.")
    
    print("\n✅ Debug complete!") 