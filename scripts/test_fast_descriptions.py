#!/usr/bin/env python3
"""
Test script to verify that description extraction works properly with speed optimization profiles.

This script tests description extraction with different speed profiles to ensure
that our performance optimizations don't break the ability to extract explanations.
"""

import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.scraper.funtrivia import FunTriviaScraper


async def test_descriptions_with_speed_profile(profile_name: str, max_questions: int = 10):
    """Test description extraction with a specific speed profile."""
    print(f"\n🔍 Testing Description Extraction: {profile_name.upper()} Profile")
    print("=" * 60)
    
    try:
        # Initialize scraper with specific speed profile
        scraper = FunTriviaScraper('config/settings.json', speed_profile=profile_name)
        await scraper.initialize()
        
        print(f"✅ Scraper initialized with {profile_name} profile")
        print(f"   Network wait: {'ENABLED' if scraper.wait_for_networkidle else 'DISABLED (faster)'}")
        print(f"   Parallel media: {'ENABLED' if scraper.parallel_media_downloads else 'DISABLED'}")
        print(f"   Fast radio: {'ENABLED' if scraper.fast_radio_button_selection else 'DISABLED'}")
        
        # Test a small batch of questions focused on description extraction
        questions = await scraper.scrape_questions(max_questions=max_questions)
        
        # Analyze description extraction success
        total_questions = len(questions)
        descriptions_found = 0
        hints_found = 0
        
        sample_descriptions = []
        
        for q in questions:
            description = q.get('Description', '') or q.get('description', '')
            hint = q.get('Hint', '') or q.get('hint', '')
            
            if description:
                descriptions_found += 1
                if len(sample_descriptions) < 3:
                    sample_descriptions.append(description[:100] + "..." if len(description) > 100 else description)
            
            if hint:
                hints_found += 1
        
        # Calculate success rates
        description_rate = (descriptions_found / total_questions * 100) if total_questions > 0 else 0
        hint_rate = (hints_found / total_questions * 100) if total_questions > 0 else 0
        
        # Print results
        print(f"\n📊 Description Extraction Results:")
        print(f"   Total Questions: {total_questions}")
        print(f"   Descriptions Found: {descriptions_found} ({description_rate:.1f}%)")
        print(f"   Hints Found: {hints_found} ({hint_rate:.1f}%)")
        
        if sample_descriptions:
            print(f"\n📝 Sample Descriptions:")
            for i, desc in enumerate(sample_descriptions, 1):
                print(f"   {i}. {desc}")
        else:
            print(f"\n⚠️ No descriptions were extracted!")
        
        # Overall assessment
        if description_rate > 80:
            status = "EXCELLENT ✅"
        elif description_rate > 60:
            status = "GOOD 👍"
        elif description_rate > 30:
            status = "FAIR ⚠️"
        else:
            status = "POOR ❌"
        
        print(f"\n🎯 Description Extraction Status: {status}")
        
        await scraper.close()
        
        return {
            'profile': profile_name,
            'success': True,
            'total_questions': total_questions,
            'descriptions_found': descriptions_found,
            'description_rate': description_rate,
            'status': status
        }
        
    except Exception as e:
        print(f"❌ Error testing {profile_name}: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'profile': profile_name,
            'success': False,
            'error': str(e),
            'total_questions': 0,
            'descriptions_found': 0,
            'description_rate': 0,
            'status': 'FAILED'
        }


async def main():
    """Test description extraction across different speed profiles."""
    print("🔬 FunTrivia Description Extraction Test")
    print("Testing if speed optimizations break description extraction...")
    print("=" * 70)
    
    # Test different speed profiles
    profiles_to_test = [
        ('normal', 8),       # baseline
        ('fast', 10),        # optimized
        ('aggressive', 12),  # high speed
    ]
    
    results = []
    
    for profile, batch_size in profiles_to_test:
        try:
            result = await test_descriptions_with_speed_profile(profile, batch_size)
            results.append(result)
            
            # Brief pause between tests
            if profile != profiles_to_test[-1][0]:  # Not the last test
                print(f"\n⏳ Waiting 20 seconds before next test...")
                await asyncio.sleep(20)
                
        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
            break
        except Exception as e:
            print(f"❌ Test failed for {profile}: {e}")
            continue
    
    # Generate summary report
    print(f"\n📈 DESCRIPTION EXTRACTION SUMMARY")
    print("=" * 70)
    
    successful_results = [r for r in results if r['success']]
    
    if successful_results:
        print("Profile Performance Summary:")
        print("-" * 50)
        
        for result in successful_results:
            print(f"{result['profile']:12}: {result['descriptions_found']:2d}/{result['total_questions']:2d} descriptions ({result['description_rate']:5.1f}%) - {result['status']}")
        
        # Check if speed optimizations broke description extraction
        normal_result = next((r for r in successful_results if r['profile'] == 'normal'), None)
        fast_results = [r for r in successful_results if r['profile'] in ['fast', 'aggressive']]
        
        if normal_result and fast_results:
            normal_rate = normal_result['description_rate']
            fast_rates = [r['description_rate'] for r in fast_results]
            avg_fast_rate = sum(fast_rates) / len(fast_rates)
            
            print(f"\n🔍 Speed Impact Analysis:")
            print(f"   Normal Profile: {normal_rate:.1f}% descriptions")
            print(f"   Fast Profiles Avg: {avg_fast_rate:.1f}% descriptions")
            
            if avg_fast_rate >= normal_rate * 0.9:  # Within 10%
                print(f"   ✅ RESULT: Speed optimizations preserve description extraction!")
            elif avg_fast_rate >= normal_rate * 0.7:  # Within 30%
                print(f"   ⚠️ RESULT: Minor impact on description extraction (acceptable)")
            else:
                print(f"   ❌ RESULT: Speed optimizations significantly hurt description extraction!")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 50)
    
    best_performing = max(successful_results, key=lambda x: x['description_rate']) if successful_results else None
    
    if best_performing:
        print(f"Best description extraction: {best_performing['profile']} profile ({best_performing['description_rate']:.1f}%)")
        
        if best_performing['description_rate'] > 80:
            print(f"✅ Recommended for description-focused scraping: --speed-profile {best_performing['profile']}")
        else:
            print(f"⚠️ All profiles showing low description extraction - may need investigation")
    
    print(f"\nTo verify CSV saving:")
    print(f"  Check output/multiple_choice_questions.csv for Description and Hint columns")


if __name__ == "__main__":
    # Run the description extraction test
    asyncio.run(main()) 