#!/usr/bin/env python3
"""
Debug script to capture the actual HTML structure of FunTrivia results pages.
This will help us understand the exact format and fix the description extraction.
"""

import asyncio
import logging
from playwright.async_api import async_playwright

async def debug_results_page():
    """Capture and analyze a FunTrivia results page structure."""
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Go to a known quiz
            quiz_url = "https://www.funtrivia.com/quiz/entertainment/comics-from-yesteryear-381373.html"
            logger.info(f"Loading quiz: {quiz_url}")
            await page.goto(quiz_url, wait_for="networkidle")
            
            # Select some answers quickly
            logger.info("Selecting answers...")
            for i in range(1, 6):  # Just first 5 questions
                try:
                    radio_selector = f'input[name="q{i}"][type="radio"]'
                    await page.click(radio_selector, timeout=2000)
                    logger.info(f"Selected answer for question {i}")
                except:
                    logger.warning(f"Could not select answer for question {i}")
            
            # Submit the quiz
            logger.info("Submitting quiz...")
            submit_button = page.locator('input[type="submit"][value*="Submit"]')
            await submit_button.click()
            
            # Wait for results page
            logger.info("Waiting for results page...")
            await page.wait_for_load_state("networkidle", timeout=30000)
            
            # Get the full page content
            logger.info("Capturing page content...")
            full_content = await page.content()
            
            # Save to file for analysis
            with open("debug_results_page.html", "w", encoding="utf-8") as f:
                f.write(full_content)
            
            # Also get just the text content
            text_content = await page.inner_text("body")
            with open("debug_results_text.txt", "w", encoding="utf-8") as f:
                f.write(text_content)
            
            logger.info("✅ Saved results page HTML to debug_results_page.html")
            logger.info("✅ Saved results page text to debug_results_text.txt")
            
            # Try to find result blocks
            logger.info("Analyzing result structure...")
            
            # Test different selectors
            selectors_to_test = [
                "table tr",
                ".questionReview", 
                "tr",
                "div",
                "p",
                "*:has-text('correct answer')",
                "*:has-text('The correct answer was')"
            ]
            
            for selector in selectors_to_test:
                try:
                    elements = await page.locator(selector).all()
                    logger.info(f"Selector '{selector}': found {len(elements)} elements")
                    
                    if selector == "*:has-text('The correct answer was')" and elements:
                        # Get text from first few elements that contain "correct answer"
                        for i, elem in enumerate(elements[:3]):
                            text = await elem.inner_text()
                            logger.info(f"  Element {i+1} text: {text[:200]}...")
                            
                except Exception as e:
                    logger.warning(f"Selector '{selector}' failed: {e}")
            
        except Exception as e:
            logger.error(f"Error: {e}")
        
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_results_page()) 