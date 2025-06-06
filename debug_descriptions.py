#!/usr/bin/env python3
"""
Debug script to analyze FunTrivia results page structure for description extraction.
This will help us understand why descriptions aren't being found.
"""

import asyncio
import logging
from playwright.async_api import async_playwright

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def debug_funtrivia_results_page():
    """
    Open a FunTrivia quiz, complete it, and analyze the results page structure
    to understand how descriptions/explanations are displayed.
    """
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False, slow_mo=1000)  # Visible browser for debugging
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            # Navigate to a known photo quiz
            test_quiz_url = "https://www.funtrivia.com/quiz/geography/great-lakes-416213.html"
            print(f"🔍 Loading quiz: {test_quiz_url}")
            
            await page.goto(test_quiz_url, timeout=60000)
            await page.wait_for_load_state('networkidle')
            
            print("✅ Quiz page loaded successfully")
            
            # Check if quiz is already started or needs to be started
            start_button = await page.query_selector('input[type="submit"][value*="Start"]')
            if start_button:
                print("🎯 Starting quiz...")
                await start_button.click()
                await page.wait_for_load_state('networkidle')
            else:
                print("🎯 Quiz appears to already be started")
            
            # Find and click radio buttons for all questions (select first option for each)
            print("📝 Selecting answers for all questions...")
            
            # Find all radio buttons
            radio_buttons = await page.query_selector_all('input[type="radio"]')
            print(f"Found {len(radio_buttons)} radio buttons")
            
            # Select first option for each question (pattern-based)
            questions_answered = 0
            for i in range(1, 21):  # Assuming 20 questions max
                try:
                    # Try different patterns for question numbering
                    patterns = [f'q{i}a', f'q{i}', f'Q{i}A', f'Q{i}']
                    
                    for pattern in patterns:
                        radio = await page.query_selector(f'input[name="{pattern}"]')
                        if radio:
                            # Check if already visible
                            is_visible = await radio.is_visible()
                            if not is_visible:
                                # Try to make it visible
                                await page.evaluate('''(radio) => {
                                    radio.style.display = 'block';
                                    radio.style.visibility = 'visible';
                                    radio.style.opacity = '1';
                                }''', radio)
                            
                            await radio.check()
                            questions_answered += 1
                            print(f"✅ Answered question {i}")
                            break
                    
                except Exception as e:
                    print(f"⚠️ Could not answer question {i}: {e}")
                    continue
            
            print(f"📊 Answered {questions_answered} questions")
            
            # Submit the quiz
            print("🚀 Submitting quiz...")
            submit_button = await page.query_selector('input[type="submit"][value*="Submit"]')
            if submit_button:
                await submit_button.click()
                print("✅ Quiz submitted, waiting for results page...")
                
                # Wait for results page to load
                await page.wait_for_load_state('networkidle', timeout=60000)
                print("✅ Results page loaded")
                
                # Analyze the page structure
                print("\n" + "="*60)
                print("🔍 ANALYZING RESULTS PAGE STRUCTURE")
                print("="*60)
                
                # Get the entire page HTML
                page_content = await page.content()
                
                # Get all text content
                page_text = await page.evaluate('document.body.innerText')
                
                print(f"📄 Page content length: {len(page_content)} chars")
                print(f"📄 Page text length: {len(page_text)} chars")
                
                # Look for description-related keywords in the text
                description_keywords = [
                    'interesting information',
                    'explanation',
                    'trivia',
                    'fun fact',
                    'did you know',
                    'background',
                    'additional information'
                ]
                
                print("\n🔍 SEARCHING FOR DESCRIPTION KEYWORDS:")
                for keyword in description_keywords:
                    count = page_text.lower().count(keyword.lower())
                    if count > 0:
                        print(f"   ✅ Found '{keyword}': {count} occurrences")
                        
                        # Show context around keyword
                        keyword_index = page_text.lower().find(keyword.lower())
                        if keyword_index != -1:
                            start = max(0, keyword_index - 100)
                            end = min(len(page_text), keyword_index + 200)
                            context = page_text[start:end].replace('\n', ' ')
                            print(f"      Context: ...{context}...")
                    else:
                        print(f"   ❌ '{keyword}': Not found")
                
                # Analyze result blocks
                print("\n🧱 ANALYZING RESULT BLOCK STRUCTURE:")
                
                # Try different selectors for result blocks
                result_selectors = [
                    '.questionReview',
                    '.questionTable', 
                    '.result-item',
                    '.question-result',
                    'tr[class*="question"]',
                    'div[class*="question"]',
                    '.question-block',
                    'table tr',  # Generic table rows
                    '.quiz-results tr',
                    'div[id*="question"]'
                ]
                
                for selector in result_selectors:
                    elements = await page.query_selector_all(selector)
                    if elements:
                        print(f"   ✅ Selector '{selector}': Found {len(elements)} elements")
                        
                        # Analyze first element
                        if elements:
                            first_element = elements[0]
                            element_html = await first_element.inner_html()
                            element_text = await first_element.inner_text()
                            
                            print(f"      First element text: {element_text[:200]}...")
                            
                            # Look for descriptions in this element
                            if any(keyword in element_text.lower() for keyword in description_keywords):
                                print(f"      🎯 FOUND DESCRIPTION CONTENT in '{selector}'!")
                                print(f"      Full text: {element_text}")
                    else:
                        print(f"   ❌ Selector '{selector}': No elements found")
                
                # Look for tables specifically
                print("\n📊 ANALYZING TABLE STRUCTURE:")
                tables = await page.query_selector_all('table')
                print(f"Found {len(tables)} tables")
                
                for i, table in enumerate(tables):
                    table_text = await table.inner_text()
                    if len(table_text) > 100:  # Only analyze substantial tables
                        print(f"\n   Table {i+1} text preview: {table_text[:300]}...")
                        
                        # Check if this table contains descriptions
                        if any(keyword in table_text.lower() for keyword in description_keywords):
                            print(f"   🎯 Table {i+1} contains description keywords!")
                            
                            # Get table HTML structure
                            table_html = await table.inner_html()
                            print(f"   Table {i+1} HTML structure preview: {table_html[:500]}...")
                
                # Save page content for further analysis
                with open('debug_results_page.html', 'w', encoding='utf-8') as f:
                    f.write(page_content)
                print("\n💾 Saved full page HTML to 'debug_results_page.html'")
                
                with open('debug_results_text.txt', 'w', encoding='utf-8') as f:
                    f.write(page_text)
                print("💾 Saved page text to 'debug_results_text.txt'")
                
                print("\n🎯 MANUAL INSPECTION RECOMMENDED:")
                print("   1. Check 'debug_results_page.html' in browser")
                print("   2. Search for description/explanation content")
                print("   3. Note the HTML structure around descriptions")
                print("   4. Update extraction logic based on findings")
                
                # Keep browser open for manual inspection
                print("\n⏸️ Browser will remain open for manual inspection...")
                print("   Press Enter to close when done analyzing...")
                input()
                
            else:
                print("❌ Could not find submit button")
                
        except Exception as e:
            print(f"❌ Error during debugging: {e}")
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_funtrivia_results_page()) 