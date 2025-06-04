"""
Question Type Classification Module

This module handles the classification of questions into different types:
- true_false: Questions with binary True/False, Yes/No, etc. answers
- multiple_choice: Questions with multiple options
- sound: Questions involving audio content

The classifier uses multiple strategies to accurately determine question types.
"""

import re
import logging
from typing import List, Dict, Set
import sys
import os

# Handle imports whether running as module or directly
try:
    from ..constants import (
        TRUE_FALSE_SYNONYMS, TRUE_FALSE_PATTERNS, QUESTION_PATTERNS, THRESHOLDS
    )
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from constants import (
        TRUE_FALSE_SYNONYMS, TRUE_FALSE_PATTERNS, QUESTION_PATTERNS, THRESHOLDS
    )


class QuestionClassifier:
    """
    Classifies questions into different types based on content and options.
    
    Uses a multi-strategy approach with priority ordering to ensure accurate
    classification while avoiding false positives.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._all_tf_synonyms = self._flatten_synonyms()
    
    def _flatten_synonyms(self) -> List[str]:
        """Flatten True/False synonyms into a single list for quick checking."""
        synonyms = []
        for category in TRUE_FALSE_SYNONYMS.values():
            synonyms.extend(category)
        return synonyms
    
    def classify(self, question_text: str, options: List[str]) -> str:
        """
        Classify a question into its appropriate type.
        
        Args:
            question_text: The question text to analyze
            options: List of answer options
            
        Returns:
            str: 'true_false', 'multiple_choice', or 'sound'
        """
        # Clean options for analysis
        clean_options = [opt.strip().lower() for opt in options if opt.strip()]
        
        self.logger.debug(f"Classifying question with {len(clean_options)} options: {options}")
        
        # Strategy 0: Sound detection (highest priority)
        if self._is_sound_question(question_text):
            self.logger.info(f"Classified as Sound question: {question_text[:50]}...")
            return "sound"
        
        # Only process binary questions for True/False classification
        if len(clean_options) == 2:
            tf_result = self._classify_binary_question(question_text, clean_options, options)
            if tf_result:
                return tf_result
        
        # Default classification
        return self._default_classification(clean_options, question_text, options)
    
    def _is_sound_question(self, question_text: str) -> bool:
        """Check if question involves audio/sound content."""
        question_lower = question_text.lower()
        return any(indicator in question_lower for indicator in QUESTION_PATTERNS['sound_indicators'])
    
    def _classify_binary_question(self, question_text: str, clean_options: List[str], original_options: List[str]) -> str:
        """
        Classify a question with exactly 2 options.
        
        Returns:
            str: 'true_false' if classified as T/F, None if should use default classification
        """
        option1, option2 = clean_options
        
        # Strategy 1: Direct synonym matching
        if self._is_direct_tf_match(option1, option2, original_options):
            return "true_false"
        
        # Strategy 2: Common pattern matching
        if self._is_pattern_match(option1, option2, original_options):
            return "true_false"
        
        # Strategy 3: Question text analysis (with factual exclusions)
        if self._is_question_pattern_match(question_text, clean_options, original_options):
            return "true_false"
        
        # Strategy 4: Flag suspicious cases
        self._check_suspicious_binary(question_text, clean_options, original_options)
        
        return None  # Let default classification handle it
    
    def _is_direct_tf_match(self, option1: str, option2: str, original_options: List[str]) -> bool:
        """Check for direct True/False synonym matches."""
        if option1 in self._all_tf_synonyms and option2 in self._all_tf_synonyms:
            # Verify they're from opposite categories
            is_opposite = (
                (option1 in TRUE_FALSE_SYNONYMS['true'] and option2 in TRUE_FALSE_SYNONYMS['false']) or
                (option1 in TRUE_FALSE_SYNONYMS['false'] and option2 in TRUE_FALSE_SYNONYMS['true'])
            )
            
            if is_opposite:
                self.logger.info(f"Classified as True/False: {original_options} (direct synonym match)")
                return True
        
        return False
    
    def _is_pattern_match(self, option1: str, option2: str, original_options: List[str]) -> bool:
        """Check for common True/False patterns."""
        for true_opt, false_opt in TRUE_FALSE_PATTERNS:
            if ((option1 == true_opt and option2 == false_opt) or 
                (option1 == false_opt and option2 == true_opt)):
                self.logger.info(f"Classified as True/False: {original_options} (pattern match)")
                return True
        
        return False
    
    def _is_question_pattern_match(self, question_text: str, clean_options: List[str], original_options: List[str]) -> bool:
        """Check if question text suggests True/False with factual exclusions."""
        question_lower = question_text.lower()
        
        # Check for True/False indicators
        has_tf_indicators = any(
            re.search(pattern, question_lower) 
            for pattern in QUESTION_PATTERNS['true_false_indicators']
        )
        
        # Check for factual question exclusions
        is_factual = any(
            re.search(pattern, question_lower) 
            for pattern in QUESTION_PATTERNS['factual_indicators']
        )
        
        # Must have T/F indicators, not be factual, and have short options
        if (has_tf_indicators and 
            not is_factual and 
            all(len(opt) <= THRESHOLDS['short_option_length'] for opt in clean_options)):
            
            self.logger.info(f"Classified as True/False: {original_options} (question pattern + 2 short options)")
            return True
        
        return False
    
    def _check_suspicious_binary(self, question_text: str, clean_options: List[str], original_options: List[str]) -> None:
        """Check for suspicious binary questions that might be misclassified."""
        # Only check non-factual questions with short options
        question_lower = question_text.lower()
        is_factual = any(
            re.search(pattern, question_lower) 
            for pattern in QUESTION_PATTERNS['factual_indicators']
        )
        
        if (not is_factual and 
            all(len(opt) <= THRESHOLDS['medium_option_length'] for opt in clean_options)):
            
            # Calculate option similarity
            similarity = self._calculate_similarity(clean_options[0], clean_options[1])
            
            if similarity > THRESHOLDS['similarity_threshold']:
                self.logger.warning(f"Suspicious binary question detected: '{question_text[:50]}...' with options {original_options}")
                self.logger.warning(f"Consider reviewing if this should be True/False instead of Multiple Choice")
    
    def _calculate_similarity(self, option1: str, option2: str) -> float:
        """Calculate similarity between two options using character overlap."""
        option1_chars = set(option1)
        option2_chars = set(option2)
        common_chars = len(option1_chars & option2_chars)
        total_chars = len(option1_chars | option2_chars)
        return common_chars / total_chars if total_chars > 0 else 0
    
    def _default_classification(self, clean_options: List[str], question_text: str, original_options: List[str]) -> str:
        """Handle default classification logic."""
        if len(clean_options) > 2:
            self.logger.debug(f"Classified as Multiple Choice: {len(clean_options)} options")
        elif len(clean_options) == 2:
            self.logger.warning(f"Ambiguous classification - defaulting to Multiple Choice for: '{question_text[:50]}...' with options {original_options}")
        
        return "multiple_choice"


# Convenience function for backward compatibility
def detect_question_type(question_text: str, options: List[str]) -> str:
    """
    Convenience function to classify a question type.
    
    Args:
        question_text: The question text to analyze
        options: List of answer options
        
    Returns:
        str: 'true_false', 'multiple_choice', or 'sound'
    """
    classifier = QuestionClassifier()
    return classifier.classify(question_text, options) 