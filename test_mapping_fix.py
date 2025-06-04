#!/usr/bin/env python3
"""
Test script to verify the updated FunTrivia domain/topic mapping logic.
"""
import asyncio
import sys
import os
sys.path.append('src')

from scraper.funtrivia import FunTriviaScraper


async def test_mapping_logic():
    """Test the updated domain and topic extraction logic."""
    print("🧪 Testing updated FunTrivia domain/topic mapping logic...")
    
    # Test URLs from different FunTrivia categories based on web search results
    test_urls = [
        "https://www.funtrivia.com/en/Sports/Sports-Rules-9783.html",  # Sports → Sports Rules
        "https://www.funtrivia.com/en/World/US-Currency-5888.html",   # Geography → U.S. Currency  
        "https://www.funtrivia.com/en/Entertainment/Amateur-Radio-DX-6807.html",  # Culture → Amateur Radio
        "https://www.funtrivia.com/trivia-quiz/General/Whats-up-in-this-Quiz-4-409598.html",  # General quiz
    ]
    
    # Initialize scraper
    scraper = FunTriviaScraper("config/settings.json")
    
    try:
        await scraper.initialize()
        
        for i, url in enumerate(test_urls, 1):
            print(f"\n📍 Test {i}: {url}")
            
            # Create a context and page for testing
            context = await scraper.browser.new_context(
                user_agent=scraper._get_random_user_agent()
            )
            page = await context.new_page()
            
            try:
                # Load the page
                await page.goto(url, timeout=30000)
                await page.wait_for_load_state('networkidle', timeout=15000)
                
                # Extract domain and topic using the updated logic
                domain = await scraper._get_quiz_domain(page)
                topic = await scraper._get_quiz_topic(page)
                
                # Map to standardized values
                mapped_domain = scraper.map_domain(domain)
                mapped_topic = scraper.map_topic(topic)
                
                print(f"   Raw Domain: '{domain}' → Mapped: '{mapped_domain}'")
                print(f"   Raw Topic: '{topic}' → Mapped: '{mapped_topic}'")
                
                # Check if mapping is reasonable
                expected_mappings = {
                    "Sports-Rules": ("Sports", "General"),
                    "US-Currency": ("Geography", "Geography"), 
                    "Amateur-Radio": ("Culture", "Technology"),
                    "Whats-up": ("Culture", "General")
                }
                
                # Find which test this URL represents
                for key, (exp_domain, exp_topic) in expected_mappings.items():
                    if key.lower() in url.lower():
                        if mapped_domain == exp_domain and mapped_topic == exp_topic:
                            print(f"   ✅ Mapping correct: {exp_domain} → {exp_topic}")
                        else:
                            print(f"   ⚠️  Expected: {exp_domain} → {exp_topic}, Got: {mapped_domain} → {mapped_topic}")
                        break
                
            except Exception as e:
                print(f"   ❌ Error testing URL: {e}")
            finally:
                await context.close()
                
        print(f"\n✅ Mapping test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(test_mapping_logic()) 