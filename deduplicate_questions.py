#!/usr/bin/env python3
"""
Script to remove duplicate questions from CSV files.
Deduplicates based on question text + correct answer combination.
"""

import pandas as pd
import os
from pathlib import Path
import hashlib


def create_question_signature(row):
    """Create a unique signature for a question based on text and correct answer."""
    question = str(row.get('Question', '')).strip().lower()
    answer = str(row.get('CorrectAnswer', '')).strip().lower()
    
    # Create a hash of question + answer for deduplication
    signature = f"{question}|{answer}"
    return hashlib.md5(signature.encode()).hexdigest()


def deduplicate_csv_file(csv_path: Path):
    """Remove duplicates from a single CSV file."""
    if not csv_path.exists():
        print(f"📂 {csv_path.name} does not exist - skipping")
        return
    
    # Read CSV
    df = pd.read_csv(csv_path)
    original_count = len(df)
    
    if original_count == 0:
        print(f"📄 {csv_path.name}: Empty file - skipping")
        return
    
    print(f"📄 Processing {csv_path.name}: {original_count} questions")
    
    # Create signatures for deduplication
    df['_signature'] = df.apply(create_question_signature, axis=1)
    
    # Find duplicates
    duplicates = df[df.duplicated(subset=['_signature'], keep=False)]
    
    if len(duplicates) > 0:
        print(f"  🔍 Found {len(duplicates)} duplicate entries")
        
        # Show some examples
        unique_duplicates = duplicates['_signature'].unique()[:3]
        for sig in unique_duplicates:
            dup_group = duplicates[duplicates['_signature'] == sig]
            example = dup_group.iloc[0]
            print(f"    📋 Duplicate: \"{example['Question'][:60]}...\" ({len(dup_group)} copies)")
    
    # Remove duplicates (keep first occurrence)
    df_deduplicated = df.drop_duplicates(subset=['_signature'], keep='first')
    
    # Remove the signature column
    df_deduplicated = df_deduplicated.drop(columns=['_signature'])
    
    final_count = len(df_deduplicated)
    removed_count = original_count - final_count
    
    if removed_count > 0:
        # Create backup
        backup_path = csv_path.with_suffix('.before_dedup.csv')
        df.drop(columns=['_signature']).to_csv(backup_path, index=False)
        print(f"  💾 Created backup: {backup_path.name}")
        
        # Save deduplicated version
        df_deduplicated.to_csv(csv_path, index=False)
        print(f"  ✅ Removed {removed_count} duplicates")
        print(f"  📊 Final count: {final_count} questions")
    else:
        print(f"  ✅ No duplicates found")
    
    return {
        'original_count': original_count,
        'final_count': final_count,
        'removed_count': removed_count
    }


def clean_descriptions(csv_path: Path):
    """Clean up meta information from descriptions."""
    if not csv_path.exists():
        return
    
    df = pd.read_csv(csv_path)
    
    if 'Description' not in df.columns:
        return
    
    cleaned_count = 0
    
    # Clean meta information patterns
    for idx, desc in enumerate(df['Description']):
        if pd.isna(desc):
            continue
            
        original_desc = str(desc)
        cleaned_desc = original_desc
        
        # Remove "Question by player X" patterns
        import re
        cleaned_desc = re.sub(r'Question by player \w+\.?', '', cleaned_desc, flags=re.IGNORECASE)
        cleaned_desc = re.sub(r'Submitted by \w+\.?', '', cleaned_desc, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        cleaned_desc = ' '.join(cleaned_desc.split())
        cleaned_desc = cleaned_desc.strip()
        
        if cleaned_desc != original_desc:
            df.at[idx, 'Description'] = cleaned_desc
            cleaned_count += 1
    
    if cleaned_count > 0:
        df.to_csv(csv_path, index=False)
        print(f"  🧹 Cleaned {cleaned_count} descriptions")
    
    return cleaned_count


def main():
    """Main deduplication process."""
    print("🔄 Starting question deduplication process")
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
    
    total_stats = {
        'original_total': 0,
        'final_total': 0,
        'removed_total': 0
    }
    
    for csv_file in csv_files:
        csv_path = output_dir / csv_file
        print(f"\n📁 Processing {csv_file}")
        print("-" * 30)
        
        # Deduplicate
        stats = deduplicate_csv_file(csv_path)
        
        if stats:
            total_stats['original_total'] += stats['original_count']
            total_stats['final_total'] += stats['final_count']
            total_stats['removed_total'] += stats['removed_count']
        
        # Clean descriptions
        if csv_path.exists():
            clean_descriptions(csv_path)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 DEDUPLICATION SUMMARY")
    print("=" * 50)
    print(f"Original questions: {total_stats['original_total']}")
    print(f"Final questions: {total_stats['final_total']}")
    print(f"Duplicates removed: {total_stats['removed_total']}")
    
    if total_stats['removed_total'] > 0:
        percentage = (total_stats['removed_total'] / total_stats['original_total']) * 100
        print(f"Reduction: {percentage:.1f}%")
        print(f"\n✅ Deduplication completed successfully!")
        print(f"💾 Backup files created with '.before_dedup.csv' suffix")
    else:
        print(f"\n✅ No duplicates found across all files")


if __name__ == "__main__":
    main() 