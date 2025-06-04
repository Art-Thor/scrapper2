import pandas as pd
import os
from typing import List, Dict, Any, Set
import logging
from pathlib import Path
import sys

# Handle imports whether running as module or directly
try:
    from ..constants import CSV_COLUMNS
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from constants import CSV_COLUMNS

class CSVHandler:
    """Handles CSV operations with appending capability and duplicate prevention."""
    
    def __init__(self, output_dir: str = "output"):
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def get_existing_keys(self, csv_file: str) -> Set[str]:
        """Get existing question keys from a CSV file to prevent duplicates."""
        csv_path = self.output_dir / csv_file
        existing_keys = set()
        
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                if 'Key' in df.columns:
                    existing_keys = set(df['Key'].dropna().astype(str))
                    self.logger.info(f"Found {len(existing_keys)} existing keys in {csv_file}")
            except Exception as e:
                self.logger.error(f"Error reading existing CSV {csv_file}: {e}")
        
        return existing_keys
    
    def filter_new_questions(self, questions: List[Dict[str, Any]], csv_file: str) -> List[Dict[str, Any]]:
        """Filter out questions that already exist in the CSV file."""
        existing_keys = self.get_existing_keys(csv_file)
        
        if not existing_keys:
            return questions
        
        new_questions = []
        for question in questions:
            if question.get('Key') not in existing_keys:
                new_questions.append(question)
            else:
                self.logger.debug(f"Skipping duplicate question: {question.get('Key')}")
        
        self.logger.info(f"Filtered {len(questions)} questions to {len(new_questions)} new questions")
        return new_questions
    
    def get_csv_columns(self, question_type: str) -> List[str]:
        """Get the required column structure for each question type."""
        return CSV_COLUMNS.get(question_type, CSV_COLUMNS['multiple_choice'])
    
    def ensure_csv_structure(self, df: pd.DataFrame, question_type: str) -> pd.DataFrame:
        """Ensure DataFrame has all required columns in the correct order."""
        required_columns = self.get_csv_columns(question_type)
        
        # Add missing columns with empty values
        for col in required_columns:
            if col not in df.columns:
                df[col] = ''
        
        # Reorder columns to match template
        df = df[required_columns]
        
        return df
    
    def append_to_csv(self, questions: List[Dict[str, Any]], csv_file: str, question_type: str) -> int:
        """Append new questions to existing CSV file or create new one."""
        if not questions:
            self.logger.info(f"No questions to append to {csv_file}")
            return 0
        
        csv_path = self.output_dir / csv_file
        
        # Filter out duplicates
        new_questions = self.filter_new_questions(questions, csv_file)
        
        if not new_questions:
            self.logger.info(f"No new questions to add to {csv_file}")
            return 0
        
        # Convert to DataFrame and ensure proper structure
        new_df = pd.DataFrame(new_questions)
        new_df = self.ensure_csv_structure(new_df, question_type)
        
        try:
            if csv_path.exists():
                # Read existing CSV and append new data
                existing_df = pd.read_csv(csv_path)
                existing_df = self.ensure_csv_structure(existing_df, question_type)
                
                # Combine and save
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df.to_csv(csv_path, index=False)
                
                self.logger.info(f"Appended {len(new_questions)} questions to existing {csv_file}")
                self.logger.info(f"Total questions in {csv_file}: {len(combined_df)}")
            else:
                # Create new CSV file
                new_df.to_csv(csv_path, index=False)
                self.logger.info(f"Created new {csv_file} with {len(new_questions)} questions")
            
            return len(new_questions)
            
        except Exception as e:
            self.logger.error(f"Error writing to CSV {csv_file}: {e}")
            return 0
    
    def get_csv_stats(self, csv_file: str) -> Dict[str, Any]:
        """Get statistics about an existing CSV file."""
        csv_path = self.output_dir / csv_file
        stats = {
            'exists': False,
            'total_questions': 0,
            'columns': [],
            'sample_keys': []
        }
        
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                stats['exists'] = True
                stats['total_questions'] = len(df)
                stats['columns'] = df.columns.tolist()
                
                if 'Key' in df.columns and len(df) > 0:
                    stats['sample_keys'] = df['Key'].head(3).tolist()
                    
            except Exception as e:
                self.logger.error(f"Error reading CSV stats for {csv_file}: {e}")
        
        return stats
    
    def backup_csv(self, csv_file: str) -> bool:
        """Create a backup of an existing CSV file."""
        csv_path = self.output_dir / csv_file
        
        if not csv_path.exists():
            return True
        
        backup_path = self.output_dir / f"{csv_path.stem}_backup_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            import shutil
            shutil.copy2(csv_path, backup_path)
            self.logger.info(f"Created backup: {backup_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error creating backup for {csv_file}: {e}")
            return False 