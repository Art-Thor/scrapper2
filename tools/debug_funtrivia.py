#!/usr/bin/env python3
"""
Debug tool to inspect FunTrivia.com HTML structure
This helps us understand the current page layout to fix our selectors
"""

import asyncio
import sys
import os
from playwright.async_api import async_playwright

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

async def debug_funtrivia_structure():
    """Debug FunTrivia page structure to understand the HTML layout."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Visible browser for debugging
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            print("🔍 Debugging FunTrivia.com structure...")
            
            # Step 1: Check main quizzes page
            print("\n📁 Step 1: Checking main quizzes page...")
            await page.goto("https://www.funtrivia.com/quizzes/", timeout=30000)
            await page.wait_for_load_state('networkidle')
            
            # Save screenshot for reference
            await page.screenshot(path="debug_main_page.png")
            print("Screenshot saved: debug_main_page.png")
            
            # Check for category links
            categories = await page.evaluate("""
                () => {
                    console.log('Looking for category links...');
                    const allLinks = Array.from(document.querySelectorAll('a'));
                    const categoryLinks = allLinks.filter(link => 
                        link.href.includes('/quiz') || 
                        link.href.includes('/trivia') ||
                        link.textContent.toLowerCase().includes('quiz')
                    ).slice(0, 10);  // Get first 10 for analysis
                    
                    return categoryLinks.map(link => ({
                        href: link.href,
                        text: link.textContent.trim(),
                        className: link.className,
                        parentClassName: link.parentElement ? link.parentElement.className : ''
                    }));
                }
            """)
            
            print(f"Found {len(categories)} potential category links:")
            for i, cat in enumerate(categories[:5]):
                print(f"  {i+1}. {cat['text'][:50]} -> {cat['href']}")
            
            # Step 2: Try to find a specific quiz page
            print("\n🎯 Step 2: Looking for quiz links...")
            quiz_links = await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a'));
                    return links.filter(link => 
                        link.href.includes('/quiz/') && 
                        !link.href.includes('create') &&
                        link.textContent.trim().length > 5
                    ).slice(0, 5).map(link => ({
                        href: link.href,
                        text: link.textContent.trim()
                    }));
                }
            """)
            
            if quiz_links:
                print(f"Found {len(quiz_links)} quiz links:")
                for quiz in quiz_links:
                    print(f"  - {quiz['text'][:50]} -> {quiz['href']}")
                
                # Step 3: Go to first quiz and analyze structure
                print(f"\n🎮 Step 3: Analyzing quiz structure...")
                first_quiz = quiz_links[0]['href']
                print(f"Going to: {first_quiz}")
                
                await page.goto(first_quiz, timeout=30000)
                await page.wait_for_load_state('networkidle')
                await page.screenshot(path="debug_quiz_page.png")
                print("Quiz page screenshot saved: debug_quiz_page.png")
                
                # Analyze quiz page structure
                quiz_structure = await page.evaluate("""
                    () => {
                        const structure = {
                            title: document.title,
                            headings: Array.from(document.querySelectorAll('h1, h2, h3')).map(h => ({
                                tag: h.tagName,
                                text: h.textContent.trim(),
                                className: h.className
                            })),
                            buttons: Array.from(document.querySelectorAll('button, input[type="button"], input[type="submit"]')).map(btn => ({
                                type: btn.tagName,
                                text: btn.textContent || btn.value || '',
                                className: btn.className,
                                id: btn.id
                            })),
                            forms: Array.from(document.querySelectorAll('form')).map(form => ({
                                action: form.action,
                                method: form.method,
                                className: form.className
                            })),
                            radioButtons: Array.from(document.querySelectorAll('input[type="radio"]')).map(radio => ({
                                name: radio.name,
                                value: radio.value,
                                id: radio.id,
                                className: radio.className
                            })),
                            labels: Array.from(document.querySelectorAll('label')).map(label => ({
                                text: label.textContent.trim(),
                                htmlFor: label.htmlFor,
                                className: label.className
                            })),
                            divs: Array.from(document.querySelectorAll('div')).filter(div => 
                                div.textContent.toLowerCase().includes('question') ||
                                div.textContent.toLowerCase().includes('answer') ||
                                div.className.toLowerCase().includes('question') ||
                                div.className.toLowerCase().includes('quiz')
                            ).slice(0, 10).map(div => ({
                                className: div.className,
                                text: div.textContent.trim().substring(0, 100),
                                children: div.children.length
                            }))
                        };
                        return structure;
                    }
                """)
                
                print("\n📊 Quiz page structure analysis:")
                print(f"Title: {quiz_structure['title']}")
                
                if quiz_structure['headings']:
                    print("\nHeadings found:")
                    for h in quiz_structure['headings'][:3]:
                        print(f"  {h['tag']}: {h['text'][:50]} (class: {h['className']})")
                
                if quiz_structure['buttons']:
                    print("\nButtons found:")
                    for btn in quiz_structure['buttons'][:5]:
                        print(f"  {btn['type']}: '{btn['text']}' (class: {btn['className']}, id: {btn['id']})")
                
                if quiz_structure['radioButtons']:
                    print(f"\nRadio buttons found: {len(quiz_structure['radioButtons'])}")
                    for radio in quiz_structure['radioButtons'][:3]:
                        print(f"  name: {radio['name']}, value: {radio['value']}, id: {radio['id']}")
                
                if quiz_structure['labels']:
                    print(f"\nLabels found: {len(quiz_structure['labels'])}")
                    for label in quiz_structure['labels'][:3]:
                        print(f"  text: '{label['text'][:30]}' (for: {label['htmlFor']})")
                
                if quiz_structure['divs']:
                    print("\nRelevant divs found:")
                    for div in quiz_structure['divs'][:3]:
                        print(f"  class: {div['className']}")
                        print(f"  text: {div['text'][:50]}...")
                
                # Try to find a start button and click it
                print("\n🚀 Step 4: Looking for start quiz functionality...")
                start_buttons = await page.query_selector_all('button, input[type="button"], input[type="submit"], a')
                
                for i, button in enumerate(start_buttons[:10]):
                    text = await button.text_content() or await button.get_attribute('value') or ''
                    if any(keyword in text.lower() for keyword in ['start', 'begin', 'play', 'take quiz']):
                        print(f"Found potential start button: '{text}' (index {i})")
                        try:
                            await button.click()
                            await page.wait_for_load_state('networkidle', timeout=10000)
                            await page.screenshot(path="debug_quiz_started.png")
                            print("Started quiz - screenshot saved: debug_quiz_started.png")
                            break
                        except Exception as e:
                            print(f"Failed to click start button: {e}")
                            continue
                
                # Analyze question page structure
                print("\n❓ Step 5: Analyzing question page structure...")
                question_structure = await page.evaluate("""
                    () => {
                        return {
                            questionTexts: Array.from(document.querySelectorAll('*')).filter(el => {
                                const text = el.textContent.trim();
                                return text.length > 10 && text.length < 200 && 
                                       text.includes('?') && 
                                       el.children.length === 0;  // Leaf nodes only
                            }).slice(0, 5).map(el => ({
                                tagName: el.tagName,
                                className: el.className,
                                text: el.textContent.trim(),
                                id: el.id
                            })),
                            allRadios: Array.from(document.querySelectorAll('input[type="radio"]')).map(radio => ({
                                name: radio.name,
                                value: radio.value,
                                id: radio.id,
                                nextSiblingText: radio.nextSibling ? radio.nextSibling.textContent : '',
                                parentText: radio.parentElement ? radio.parentElement.textContent.trim().substring(0, 50) : ''
                            })),
                            allLabels: Array.from(document.querySelectorAll('label')).map(label => ({
                                text: label.textContent.trim(),
                                htmlFor: label.htmlFor,
                                className: label.className
                            })),
                            pageText: document.body.textContent.substring(0, 500)
                        };
                    }
                """)
                
                print("\nQuestion structure analysis:")
                if question_structure['questionTexts']:
                    print("Potential question texts:")
                    for q in question_structure['questionTexts']:
                        print(f"  {q['tagName']}.{q['className']}: {q['text'][:50]}...")
                
                if question_structure['allRadios']:
                    print(f"\nAll radio buttons ({len(question_structure['allRadios'])}):")
                    for radio in question_structure['allRadios'][:5]:
                        print(f"  name: {radio['name']}, value: {radio['value']}")
                        print(f"    parent text: {radio['parentText']}")
                
                print(f"\nPage text sample: {question_structure['pageText'][:200]}...")
                
            else:
                print("❌ No quiz links found on main page")
            
        except Exception as e:
            print(f"❌ Error during debugging: {e}")
            await page.screenshot(path="debug_error.png")
            print("Error screenshot saved: debug_error.png")
        
        finally:
            await browser.close()
    
    print("\n✅ Debug complete! Check the generated screenshots and output above.")
    print("Now we can update the scraper selectors based on this analysis.")

if __name__ == "__main__":
    asyncio.run(debug_funtrivia_structure()) 