#!/usr/bin/env python3
"""
Script to add SourceURL column to existing CSV files.
Since we don't have the original URLs for existing questions, we'll add an empty column
that will be populated for new questions going forward.
"""

import pandas as pd
import os
from pathlib import Path


def add_source_url_column():
    """Add SourceURL column to existing CSV files."""
    print("🔗 Adding SourceURL column to existing CSV files")
    print("=" * 50)
    
    output_dir = Path("output")
    
    if not output_dir.exists():
        print(f"❌ Output directory {output_dir} does not exist")
        return
    
    csv_files = [
        "multiple_choice.csv",
        "true_false.csv",
        "sound.csv"
    ]
    
    for csv_file in csv_files:
        csv_path = output_dir / csv_file
        
        if not csv_path.exists():
            print(f"📂 {csv_file} does not exist - skipping")
            continue
        
        try:
            # Read the CSV file
            df = pd.read_csv(csv_path)
            original_count = len(df)
            
            print(f"\n📄 Processing {csv_file}: {original_count} questions")
            
            # Check if SourceURL column already exists
            if 'SourceURL' in df.columns:
                print(f"  ✅ SourceURL column already exists")
                continue
            
            # Create backup
            backup_path = csv_path.with_suffix('.before_url_backfill.csv')
            df.to_csv(backup_path, index=False)
            print(f"  💾 Created backup: {backup_path.name}")
            
            # Add SourceURL column with empty values for existing questions
            df['SourceURL'] = ''
            
            # Note: We could potentially try to reconstruct URLs from question metadata
            # but it would be complex and potentially inaccurate, so we'll leave them empty
            # for existing questions and populate only for new questions going forward
            
            # Save the updated CSV
            df.to_csv(csv_path, index=False)
            print(f"  ✅ Added SourceURL column")
            print(f"  📊 Structure updated: {len(df.columns)} columns")
            
        except Exception as e:
            print(f"  ❌ Error processing {csv_file}: {e}")
            continue
    
    print("\n" + "=" * 50)
    print("📊 BACKFILL SUMMARY")
    print("=" * 50)
    print("✅ SourceURL column added to all existing CSV files")
    print("🔗 Existing questions have empty URLs (will be populated for new questions)")
    print("💾 Backup files created with '.before_url_backfill.csv' suffix")
    print("\n💡 TIP: After scraping new questions, you can manually verify data quality")
    print("   by clicking the SourceURL links to see the original quiz pages")


def show_csv_structure():
    """Show the updated CSV structure with SourceURL column."""
    print("\n🗂️  UPDATED CSV STRUCTURE")
    print("=" * 50)
    
    structures = {
        'multiple_choice': [
            'Key', 'Domain', 'Topic', 'Difficulty', 'Question',
            'Option1', 'Option2', 'Option3', 'Option4', 
            'CorrectAnswer', 'Description', 'ImagePath', 'SourceURL'
        ],
        'true_false': [
            'Key', 'Domain', 'Topic', 'Difficulty', 'Question',
            'Option1', 'Option2', 'CorrectAnswer', 'Description', 'SourceURL'
        ],
        'sound': [
            'Key', 'Domain', 'Topic', 'Difficulty', 'Question',
            'Option1', 'Option2', 'Option3', 'Option4',
            'CorrectAnswer', 'Description', 'AudioPath', 'SourceURL'
        ]
    }
    
    for csv_type, columns in structures.items():
        print(f"\n📋 {csv_type.replace('_', ' ').title()}:")
        for i, col in enumerate(columns, 1):
            marker = "🆕" if col == "SourceURL" else "  "
            print(f"  {i:2d}. {marker} {col}")


if __name__ == "__main__":
    add_source_url_column()
    show_csv_structure()
    
    print("\n🎯 NEXT STEPS:")
    print("1. Run the scraper to collect new questions with URLs")
    print("2. Use the validation script to identify problematic questions")
    print("3. Click SourceURL links to manually verify question quality")
    print("4. Update your dataset based on manual verification") 