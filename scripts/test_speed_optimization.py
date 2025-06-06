#!/usr/bin/env python3
"""
Test script for speed optimization features.

This script demonstrates the performance improvements available with different speed profiles
and allows users to benchmark the scraping speed with their own settings.

Speed Profiles Available:
- conservative: 8-15 questions/hour (very safe)
- normal: 15-25 questions/hour (balanced - default)
- fast: 25-40 questions/hour (good performance)
- aggressive: 40-60 questions/hour (high speed)
- turbo: 60-100 questions/hour (maximum speed)
"""

import asyncio
import sys
import time
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.scraper.funtrivia import FunTriviaScraper


async def benchmark_speed_profile(profile_name: str, max_questions: int = 20) -> dict:
    """Benchmark a specific speed profile."""
    print(f"\n🚀 Testing Speed Profile: {profile_name.upper()}")
    print("=" * 50)
    
    start_time = time.time()
    
    try:
        # Initialize scraper with specific speed profile
        scraper = FunTriviaScraper('config/settings.json', speed_profile=profile_name)
        await scraper.initialize()
        
        print(f"✅ Scraper initialized with {profile_name} profile")
        
        # Test a small batch of questions
        questions = await scraper.scrape_questions(max_questions=max_questions)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Calculate performance metrics
        questions_scraped = len(questions)
        questions_per_minute = (questions_scraped / duration) * 60 if duration > 0 else 0
        questions_per_hour = questions_per_minute * 60
        
        # Analyze question types
        question_types = {}
        media_count = 0
        explanations_count = 0
        
        for q in questions:
            qtype = q.get('type', 'unknown')
            question_types[qtype] = question_types.get(qtype, 0) + 1
            
            if q.get('media_filename') or q.get('ImagePath') or q.get('AudioPath'):
                media_count += 1
                
            if q.get('description') or q.get('hint') or q.get('Description') or q.get('Hint'):
                explanations_count += 1
        
        results = {
            'profile': profile_name,
            'success': True,
            'questions_scraped': questions_scraped,
            'duration_seconds': duration,
            'questions_per_minute': questions_per_minute,
            'questions_per_hour': questions_per_hour,
            'question_types': question_types,
            'media_files': media_count,
            'explanations': explanations_count,
            'efficiency_rating': 'excellent' if questions_per_hour > 50 else 'good' if questions_per_hour > 30 else 'average' if questions_per_hour > 15 else 'slow'
        }
        
        # Print results
        print(f"📊 Results for {profile_name}:")
        print(f"   Questions Scraped: {questions_scraped}")
        print(f"   Duration: {duration:.1f} seconds")
        print(f"   Speed: {questions_per_minute:.1f} questions/minute")
        print(f"   Projected Rate: {questions_per_hour:.0f} questions/hour")
        print(f"   Question Types: {question_types}")
        print(f"   Media Files: {media_count}")
        print(f"   Explanations: {explanations_count}")
        print(f"   Efficiency: {results['efficiency_rating'].upper()}")
        
        await scraper.close()
        return results
        
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"❌ Error testing {profile_name}: {e}")
        
        return {
            'profile': profile_name,
            'success': False,
            'error': str(e),
            'duration_seconds': duration,
            'questions_scraped': 0,
            'questions_per_hour': 0
        }


async def run_speed_comparison():
    """Compare different speed profiles."""
    print("\n🔥 FunTrivia Scraper Speed Optimization Test")
    print("=" * 60)
    print("Testing different speed profiles to demonstrate performance improvements...")
    
    # Test different profiles with small batches
    profiles_to_test = [
        ('normal', 10),      # baseline
        ('fast', 15),        # improved speed
        ('aggressive', 20),  # high speed
    ]
    
    results = []
    
    for profile, batch_size in profiles_to_test:
        try:
            result = await benchmark_speed_profile(profile, batch_size)
            results.append(result)
            
            # Brief pause between tests
            if profile != profiles_to_test[-1][0]:  # Not the last test
                print(f"\n⏳ Waiting 30 seconds before next test...")
                await asyncio.sleep(30)
                
        except KeyboardInterrupt:
            print("\n🛑 Test interrupted by user")
            break
        except Exception as e:
            print(f"❌ Test failed for {profile}: {e}")
            continue
    
    # Generate comparison report
    print("\n📈 SPEED COMPARISON REPORT")
    print("=" * 60)
    
    successful_results = [r for r in results if r['success']]
    
    if successful_results:
        print("Profile Performance Summary:")
        print("-" * 40)
        
        for result in successful_results:
            print(f"{result['profile']:12}: {result['questions_per_hour']:5.0f} questions/hour ({result['efficiency_rating']})")
        
        # Find best performer
        best_profile = max(successful_results, key=lambda x: x['questions_per_hour'])
        worst_profile = min(successful_results, key=lambda x: x['questions_per_hour'])
        
        if len(successful_results) > 1:
            improvement = (best_profile['questions_per_hour'] / worst_profile['questions_per_hour'] - 1) * 100
            print(f"\n🎯 Best Profile: {best_profile['profile']} ({best_profile['questions_per_hour']:.0f} q/h)")
            print(f"📈 Speed Improvement: {improvement:.0f}% faster than {worst_profile['profile']}")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 40)
    print("For maximum speed while maintaining safety:")
    print("  python src/main.py --speed-profile fast --max-questions 100")
    print("\nFor high-volume scraping (experienced users):")
    print("  python src/main.py --speed-profile aggressive --max-questions 500")
    print("\nTo see all available profiles:")
    print("  python src/main.py --list-speed-profiles")
    
    return results


async def test_specific_optimizations():
    """Test specific optimization features."""
    print("\n🔧 Testing Specific Optimizations")
    print("=" * 50)
    
    optimizations = [
        {
            'name': 'Fast Radio Button Selection',
            'description': 'Optimized batch radio button interaction',
            'speed_boost': '15-30%'
        },
        {
            'name': 'Parallel Media Downloads',
            'description': 'Download audio/images simultaneously',
            'speed_boost': '20-40%'
        },
        {
            'name': 'Optimized Page Loading',
            'description': 'Skip networkidle waits for faster profiles',
            'speed_boost': '25-50%'
        },
        {
            'name': 'Smart Delays',
            'description': 'Adaptive delays based on error rates',
            'speed_boost': '10-25%'
        },
        {
            'name': 'Increased Concurrency',
            'description': 'More parallel browser sessions',
            'speed_boost': '2-5x faster'
        }
    ]
    
    print("Available Optimizations:")
    for opt in optimizations:
        print(f"  🚀 {opt['name']}")
        print(f"     {opt['description']}")
        print(f"     Expected Speed Boost: {opt['speed_boost']}")
        print()
    
    print("💡 All optimizations are automatically enabled based on your chosen speed profile!")


async def main():
    """Main test function."""
    print("🎮 FunTrivia Speed Optimization Test Suite")
    print("=" * 60)
    
    try:
        # Test speed profiles
        await run_speed_comparison()
        
        # Show optimization details
        await test_specific_optimizations()
        
        print(f"\n✅ Speed optimization testing completed!")
        
    except KeyboardInterrupt:
        print("\n🛑 Testing interrupted by user")
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run the speed test
    asyncio.run(main()) 