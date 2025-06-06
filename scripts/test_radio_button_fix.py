#!/usr/bin/env python3
"""
Quick test to verify radio button selection and description extraction are working.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.scraper.funtrivia import FunTriviaScraper


async def test_radio_and_descriptions():
    """Test radio button selection and description extraction."""
    print("🔧 Testing Radio Button Selection & Description Extraction")
    print("=" * 60)
    
    try:
        # Test with fast profile (should use standard radio selection now)
        scraper = FunTriviaScraper('config/settings.json', speed_profile='fast')
        await scraper.initialize()
        
        print(f"✅ Scraper initialized:")
        print(f"   Speed profile: {scraper.speed_profile}")
        print(f"   Fast radio buttons: {scraper.fast_radio_button_selection}")
        print(f"   Network wait: {'ENABLED' if scraper.wait_for_networkidle else 'DISABLED'}")
        
        # Test just 1-2 quizzes to verify
        questions = await scraper.scrape_questions(max_questions=10)
        
        print(f"\n📊 Results:")
        print(f"   Questions scraped: {len(questions)}")
        
        # Check for descriptions
        descriptions_found = 0
        for q in questions:
            if q.get('Description') or q.get('Hint') or q.get('description') or q.get('hint'):
                descriptions_found += 1
        
        print(f"   Descriptions found: {descriptions_found}/{len(questions)} ({descriptions_found/len(questions)*100:.1f}%)")
        
        # Show a sample if we got descriptions
        if descriptions_found > 0:
            for q in questions:
                desc = q.get('Description', '') or q.get('description', '') or q.get('Hint', '') or q.get('hint', '')
                if desc:
                    print(f"\n📝 Sample Description:")
                    print(f"   {desc[:200]}..." if len(desc) > 200 else f"   {desc}")
                    break
        
        await scraper.close()
        
        if descriptions_found > 0:
            print(f"\n✅ SUCCESS: Radio buttons and descriptions are working!")
        else:
            print(f"\n❌ ISSUE: No descriptions found - radio button selection may still be failing")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_radio_and_descriptions()) 