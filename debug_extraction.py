#!/usr/bin/env python3
"""
Debug script to inspect FunTrivia quiz page structure
"""

import asyncio
import sys
import os
from playwright.async_api import async_playwright

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.scraper.funtrivia import FunTriviaScraper

async def debug_quiz_page():
    """Debug a single quiz page to understand its structure."""
    
    scraper = FunTriviaScraper('config/settings.json')
    
    try:
        await scraper.initialize()
        
        # Get a quiz URL
        categories = await scraper._get_categories()
        if categories:
            category_url = categories[0]
            quiz_links = await scraper._get_quiz_links(category_url)
            if quiz_links:
                quiz_url = quiz_links[0]
                print(f"🔍 Debugging quiz: {quiz_url}")
                
                # Open the page
                context = await scraper.browser.new_context()
                page = await context.new_page()
                
                await page.goto(quiz_url, timeout=60000)
                await page.wait_for_load_state('networkidle', timeout=45000)
                
                # Check for start button
                start_btn = await page.query_selector('input[type="submit"][value*="Start"], input[value*="Take Quiz"], button:has-text("Start")')
                if start_btn:
                    print("📍 Found Start button, clicking...")
                    await start_btn.click()
                    await page.wait_for_load_state('networkidle', timeout=30000)
                
                # Analyze page structure
                print("\n🔍 Page Structure Analysis:")
                
                # Check for forms
                forms = await page.query_selector_all('form')
                print(f"Forms found: {len(forms)}")
                
                # Check for radio inputs
                radios = await page.query_selector_all('input[type="radio"]')
                print(f"Radio inputs found: {len(radios)}")
                
                if radios:
                    print("📻 Radio input details:")
                    for i, radio in enumerate(radios[:10]):  # First 10
                        name = await radio.get_attribute('name')
                        value = await radio.get_attribute('value')
                        print(f"  Radio {i+1}: name='{name}' value='{value}'")
                
                # Check for question blocks
                question_blocks = await page.query_selector_all('.questionBlock')
                print(f"Question blocks (.questionBlock): {len(question_blocks)}")
                
                # Check for numbered questions
                bold_elements = await page.query_selector_all('b, strong')
                numbered_questions = []
                for b in bold_elements:
                    text = await b.inner_text()
                    if text and any(char.isdigit() for char in text[:10]):
                        numbered_questions.append(text[:100])
                
                print(f"Potential numbered questions: {len(numbered_questions)}")
                if numbered_questions:
                    for i, q in enumerate(numbered_questions[:5]):
                        print(f"  Q{i+1}: {q}")
                
                # Get page HTML for manual inspection
                page_content = await page.content()
                with open('debug_page.html', 'w', encoding='utf-8') as f:
                    f.write(page_content)
                print(f"\n💾 Saved page HTML to debug_page.html for manual inspection")
                
                # Try to extract with current logic
                print(f"\n🧪 Testing current extraction logic:")
                questions = await scraper._extract_questions_robust(page)
                print(f"Questions extracted: {len(questions)}")
                
                if questions:
                    for i, q in enumerate(questions[:3]):
                        print(f"  Q{i+1}: {q.get('question', '')[:80]}...")
                        print(f"      Options: {q.get('options', [])}")
                else:
                    print("❌ No questions extracted with current logic")
                
                await context.close()
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await scraper.close()

if __name__ == '__main__':
    asyncio.run(debug_quiz_page()) 