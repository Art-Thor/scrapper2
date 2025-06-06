#!/usr/bin/env python3
"""
Cleanup script to remove Hint column from existing CSV files.
This keeps only the Description column and removes the duplicate Hint field.
"""

import pandas as pd
import os
from pathlib import Path


def cleanup_csv_files():
    """Remove Hint column from existing CSV files."""
    output_dir = Path("output")
    
    if not output_dir.exists():
        print(f"Output directory {output_dir} does not exist")
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
            # Read existing CSV
            df = pd.read_csv(csv_path)
            print(f"📄 Processing {csv_file}: {len(df)} rows")
            
            # Check if Hint column exists
            if 'Hint' not in df.columns:
                print(f"  ✅ No Hint column found - already clean")
                continue
            
            # Check if Description column exists
            if 'Description' not in df.columns:
                print(f"  ⚠️ No Description column found - keeping Hint as Description")
                df['Description'] = df['Hint']
            else:
                # If both exist, check if they're the same
                if df['Hint'].equals(df['Description']):
                    print(f"  🔄 Hint and Description are identical - removing Hint")
                else:
                    print(f"  ⚠️ Hint and Description differ - keeping Description, removing Hint")
            
            # Remove Hint column
            df = df.drop(columns=['Hint'])
            
            # Create backup
            backup_path = csv_path.with_suffix('.backup.csv')
            if csv_path.exists():
                import shutil
                shutil.copy2(csv_path, backup_path)
                print(f"  💾 Created backup: {backup_path.name}")
            
            # Save cleaned CSV
            df.to_csv(csv_path, index=False)
            print(f"  ✅ Cleaned {csv_file}: removed Hint column")
            
            # Show new structure
            print(f"  📋 New columns: {', '.join(df.columns)}")
            
        except Exception as e:
            print(f"  ❌ Error processing {csv_file}: {e}")
            continue
        
        print()


if __name__ == "__main__":
    print("🧹 CSV Cleanup: Removing duplicate Hint columns")
    print("=" * 50)
    cleanup_csv_files()
    print("✅ CSV cleanup completed!") 