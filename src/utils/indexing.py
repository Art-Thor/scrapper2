import json
import os
from typing import Dict
import logging

class QuestionIndexer:
    """Manages persistent question indexing to avoid duplicates across runs."""
    
    def __init__(self, index_file: str = "question_indices.json"):
        self.logger = logging.getLogger(__name__)
        self.index_file = index_file
        self.indices = self._load_indices()
    
    def _load_indices(self) -> Dict[str, int]:
        """Load existing indices from file."""
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r') as f:
                    indices = json.load(f)
                self.logger.info(f"Loaded existing indices: {indices}")
                return indices
            except Exception as e:
                self.logger.error(f"Error loading indices file: {e}")
        
        # Return default indices if file doesn't exist or can't be loaded
        default_indices = {
            "multiple_choice": 0,
            "true_false": 0,
            "sound": 0
        }
        self.logger.info("Using default indices (starting from 0)")
        return default_indices
    
    def _save_indices(self) -> None:
        """Save current indices to file."""
        try:
            with open(self.index_file, 'w') as f:
                json.dump(self.indices, f, indent=2)
            self.logger.info(f"Saved indices: {self.indices}")
        except Exception as e:
            self.logger.error(f"Error saving indices file: {e}")
    
    def get_next_id(self, question_type: str, domain: str = None, difficulty: str = None) -> str:
        """
        Generate the next question ID for the given type using the new standardized format.
        
        New Format: Question_{TYPE}_Parsed_{DOMAIN}_{DIFFICULTY}_{UNIQUEID}
        Examples:
        - Question_MQ_Parsed_Culture_Normal_0001
        - Question_TF_Parsed_Science_Hard_0001  
        - Question_Sound_Parsed_Nature_Easy_0001
        
        Args:
            question_type: Type of question ('multiple_choice', 'true_false', 'sound')
            domain: Mapped domain value (e.g., 'Culture', 'Science', 'Nature')
            difficulty: Mapped difficulty value (e.g., 'Easy', 'Normal', 'Hard')
            
        Returns:
            Formatted question ID string following the new localization key format
        """
        if question_type not in self.indices:
            self.indices[question_type] = 0
        
        self.indices[question_type] += 1
        current_id = self.indices[question_type]
        
        # Save immediately to prevent loss on crashes
        self._save_indices()
        
        # Map question type to prefix for the new localization key format
        type_prefix = {
            "multiple_choice": "MQ",
            "true_false": "TF", 
            "sound": "Sound"  # Changed from "SOUND" to "Sound" to match user requirements
        }.get(question_type, "MQ")
        
        # Generate question ID using the new localization key format
        # Format: Question_{TYPE}_Parsed_{DOMAIN}_{DIFFICULTY}_{UNIQUEID}
        if domain and difficulty:
            # New format with domain and difficulty
            question_id = f"Question_{type_prefix}_Parsed_{domain}_{difficulty}_{current_id:04d}"
        else:
            # Fallback to old format if domain/difficulty not provided (for backwards compatibility)
            question_id = f"Question_{type_prefix}_Parsed_{current_id:04d}"
            self.logger.warning(f"Generated question ID without domain/difficulty for {question_type}: {question_id}")
        
        self.logger.debug(f"Generated localization key {question_id} for type {question_type}")
        
        return question_id
    
    def get_current_count(self, question_type: str) -> int:
        """Get current count for a question type."""
        return self.indices.get(question_type, 0)
    
    def reset_indices(self) -> None:
        """Reset all indices to 0 (use with caution)."""
        self.indices = {
            "multiple_choice": 0,
            "true_false": 0,
            "sound": 0
        }
        self._save_indices()
        self.logger.warning("All indices have been reset to 0")
    
    def get_all_indices(self) -> Dict[str, int]:
        """Get a copy of all current indices."""
        return self.indices.copy() 