#!/usr/bin/env python3
"""
Example Category Management Workflow

This script demonstrates the complete workflow for collecting and managing
categories in the FunTrivia scraper.

Usage:
    python example_category_workflow.py
"""

import asyncio
import subprocess
import sys
import json
import os
from pathlib import Path

def run_command(command, description):
    """Run a command and display its output."""
    print(f"\n🔄 {description}")
    print(f"Command: {command}")
    print("-" * 50)
    
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Success!")
        if result.stdout:
            print(result.stdout)
    else:
        print("❌ Error!")
        if result.stderr:
            print(result.stderr)
        if result.stdout:
            print(result.stdout)
    
    print("-" * 50)
    return result.returncode == 0

def check_prerequisites():
    """Check if required files exist."""
    required_files = [
        'config/settings.json',
        'config/mappings.json',
        'collect_categories.py',
        'src/main.py'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return False
    
    print("✅ All required files found")
    return True

def analyze_collected_categories():
    """Analyze the collected categories and show summary."""
    output_dir = Path("output")
    
    files_to_check = [
        "collected_domains.csv",
        "collected_topics.csv", 
        "all_categories.json"
    ]
    
    print("\n📊 COLLECTED CATEGORIES ANALYSIS")
    print("=" * 50)
    
    for filename in files_to_check:
        file_path = output_dir / filename
        if file_path.exists():
            print(f"\n📁 {filename}:")
            if filename.endswith('.csv'):
                # Show first few lines of CSV
                with open(file_path, 'r') as f:
                    lines = f.readlines()[:10]  # First 10 lines
                    for line in lines:
                        print(f"  {line.strip()}")
                    if len(lines) == 10:
                        print("  ... (more lines)")
            elif filename.endswith('.json'):
                # Show summary of JSON
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    if 'summary' in data:
                        summary = data['summary']
                        print(f"  Total categories: {summary.get('total_category_urls', 'N/A')}")
                        print(f"  Total quiz URLs: {summary.get('total_quiz_urls', 'N/A')}")
                        print(f"  Unique domains: {summary.get('unique_domains', 'N/A')}")
                        print(f"  Unique topics: {summary.get('unique_topics', 'N/A')}")
                        
                        if 'top_domains' in summary:
                            print("  Top domains:")
                            for domain, count in list(summary['top_domains'].items())[:5]:
                                print(f"    {domain}: {count}")
        else:
            print(f"\n❌ {filename} not found")

def show_mapping_suggestions():
    """Show suggestions for updating mappings based on collected data."""
    print("\n💡 MAPPING UPDATE SUGGESTIONS")
    print("=" * 50)
    print("1. Review the collected categories in output/collected_domains.csv")
    print("2. Review the collected topics in output/collected_topics.csv")
    print("3. Update config/mappings.json with new categories:")
    print()
    print("Example additions to config/mappings.json:")
    print("""
{
  "domain_mapping": {
    "Nature": ["animals", "wildlife", "pets", "YOUR_NEW_NATURE_CATEGORY"],
    "Science": ["science", "physics", "chemistry", "YOUR_NEW_SCIENCE_CATEGORY"],
    "Culture": ["music", "movies", "literature", "YOUR_NEW_CULTURE_CATEGORY"]
  },
  "topic_mapping": {
    "Animals": ["animals", "pets", "mammals", "YOUR_NEW_ANIMAL_TOPIC"],
    "Music": ["music", "songs", "bands", "YOUR_NEW_MUSIC_TOPIC"],
    "Movies": ["movies", "films", "cinema", "YOUR_NEW_MOVIE_TOPIC"]
  }
}
    """)

def main():
    """Run the complete category management workflow."""
    print("🎯 FunTrivia Category Management Workflow")
    print("=" * 60)
    
    # Step 1: Check prerequisites
    print("\n📋 Step 1: Checking Prerequisites")
    if not check_prerequisites():
        print("Please ensure all required files are present before continuing.")
        return
    
    # Step 2: Collect categories
    print("\n🔍 Step 2: Collecting Categories from the Site")
    print("This may take several minutes as it analyzes the entire site...")
    
    success = run_command(
        "python collect_categories.py --output-format both --output-dir output",
        "Collecting all categories from FunTrivia"
    )
    
    if not success:
        print("❌ Category collection failed. Please check the error messages above.")
        return
    
    # Step 3: Analyze collected data
    print("\n📊 Step 3: Analyzing Collected Categories")
    analyze_collected_categories()
    
    # Step 4: Show mapping suggestions
    show_mapping_suggestions()
    
    # Step 5: Test strict mapping
    print("\n🧪 Step 5: Testing Strict Mapping Mode")
    print("Now let's test the strict mapping mode with a small sample...")
    
    success = run_command(
        "python src/main.py --strict-mapping --max-questions 5 --dry-run",
        "Testing strict mapping with 5 questions (dry run)"
    )
    
    if success:
        print("✅ Great! Your current mappings handle the sample questions.")
        print("You can now run the full scraper with strict mapping enabled.")
        print("\nTo run the full scraper:")
        print("  python src/main.py --strict-mapping")
    else:
        print("⚠️  Some categories are not mapped yet.")
        print("Review the error messages above and update your config/mappings.json file.")
        print("Then run this script again or test with:")
        print("  python src/main.py --strict-mapping --max-questions 5 --dry-run")
    
    print("\n🎉 Category Management Workflow Complete!")
    print("=" * 60)
    print("Next steps:")
    print("1. Review the files in output/ directory")
    print("2. Update config/mappings.json with any missing categories")
    print("3. Test with: python src/main.py --strict-mapping --dry-run")
    print("4. Run full scraper: python src/main.py --strict-mapping")

if __name__ == '__main__':
    main() 