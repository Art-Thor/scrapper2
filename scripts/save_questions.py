#!/usr/bin/env python3
"""
Script to run the scraper and save questions to CSV files.
This will actually complete the scraping process and save data.
"""

import subprocess
import sys
import time

def run_scraper_and_save():
    """Run the scraper with a small number of questions and let it complete."""
    print("🚀 Starting scraper to collect and save questions...")
    print("⏳ This will take a few minutes - please don't interrupt!")
    print("📝 The scraper will save questions to CSV files when it completes.")
    
    try:
        # Run the main scraper with 10 questions
        result = subprocess.run([
            sys.executable, "src/main.py", 
            "--max-questions", "10"
        ], capture_output=True, text=True, timeout=300)  # 5 minute timeout
        
        print("\n" + "="*60)
        print("SCRAPER OUTPUT:")
        print("="*60)
        print(result.stdout)
        
        if result.stderr:
            print("\nERRORS/WARNINGS:")
            print(result.stderr)
        
        print(f"\nReturn code: {result.returncode}")
        
        if result.returncode == 0:
            print("✅ Scraper completed successfully!")
            print("📁 Check the 'output' directory for CSV files.")
        else:
            print("❌ Scraper encountered issues.")
            
    except subprocess.TimeoutExpired:
        print("⏰ Scraper timed out after 5 minutes.")
    except Exception as e:
        print(f"❌ Error running scraper: {e}")

if __name__ == '__main__':
    run_scraper_and_save() 