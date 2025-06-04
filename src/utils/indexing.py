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
    
    def get_next_id(self, question_type: str) -> str:
        """Get the next question ID for the given type."""
        if question_type not in self.indices:
            self.indices[question_type] = 0
        
        self.indices[question_type] += 1
        current_id = self.indices[question_type]
        
        # Save immediately to prevent loss on crashes
        self._save_indices()
        
        # Format the ID based on question type
        type_prefix = {
            "multiple_choice": "MQ",
            "true_false": "TF", 
            "sound": "SOUND"
        }.get(question_type, "MQ")
        
        question_id = f"Question_{type_prefix}_Parsed_{current_id:04d}"
        self.logger.debug(f"Generated ID {question_id} for type {question_type}")
        
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