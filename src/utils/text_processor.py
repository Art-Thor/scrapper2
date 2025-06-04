"""
Text Processing Utilities

This module provides centralized text processing functions for cleaning,
normalizing, and extracting information from scraped content.
"""

import re
from typing import List, Optional
import sys
import os

# Handle imports whether running as module or directly
try:
    from ..constants import TEXT_CLEANUP_PATTERNS
except ImportError:
    # Add parent directory to path for direct execution
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from constants import TEXT_CLEANUP_PATTERNS


class TextProcessor:
    """
    Handles text processing operations for scraped content.
    
    Provides methods for cleaning question text, processing hints and descriptions,
    and normalizing various text fields.
    """
    
    @staticmethod
    def clean_question_text(text: str) -> str:
        """
        Clean question text by removing prefixes and normalizing format.
        
        Args:
            text: Raw question text
            
        Returns:
            str: Cleaned question text
        """
        if not text:
            return ""
        
        cleaned = text.strip()
        
        # Remove numbered prefixes (e.g., "1. What is...")
        for prefix_pattern in TEXT_CLEANUP_PATTERNS['question_prefixes']:
            cleaned = re.sub(prefix_pattern, '', cleaned).strip()
        
        return cleaned
    
    @staticmethod
    def clean_hint_text(text: str) -> str:
        """
        Clean hint text by removing common prefixes.
        
        Args:
            text: Raw hint text
            
        Returns:
            str: Cleaned hint text
        """
        if not text:
            return ""
        
        cleaned = text.strip()
        
        # Remove common hint prefixes
        for prefix in TEXT_CLEANUP_PATTERNS['hint_prefixes']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        return cleaned
    
    @staticmethod
    def clean_description_text(text: str) -> str:
        """
        Clean description/explanation text by removing prefixes and normalizing.
        
        Args:
            text: Raw description text
            
        Returns:
            str: Cleaned description text
        """
        if not text:
            return ""
        
        cleaned = text.strip()
        
        # Remove common description prefixes
        for prefix in TEXT_CLEANUP_PATTERNS['description_prefixes']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        return cleaned
    
    @staticmethod
    def normalize_option_text(text: str) -> str:
        """
        Normalize answer option text.
        
        Args:
            text: Raw option text
            
        Returns:
            str: Normalized option text
        """
        if not text:
            return ""
        
        # Remove leading option markers (a), b), etc.)
        cleaned = re.sub(r'^[a-d]\)?\s*', '', text.strip(), flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    @staticmethod
    def extract_numbered_options(text: str) -> List[str]:
        """
        Extract numbered options from text content.
        
        Args:
            text: Text containing numbered options
            
        Returns:
            List[str]: Extracted options
        """
        options = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            # Match patterns like "a) Option text" or "A. Option text"
            match = re.match(r'^[a-d][.)]\s*(.+)', line, re.IGNORECASE)
            if match:
                options.append(match.group(1).strip())
        
        return options
    
    @staticmethod
    def is_valid_question_text(text: str, min_length: int = 10, max_length: int = 500) -> bool:
        """
        Validate if text is a reasonable question.
        
        Args:
            text: Question text to validate
            min_length: Minimum acceptable length
            max_length: Maximum acceptable length
            
        Returns:
            bool: True if text appears to be a valid question
        """
        if not text or not text.strip():
            return False
        
        text = text.strip()
        
        # Check length bounds
        if len(text) < min_length or len(text) > max_length:
            return False
        
        # Very basic content validation
        # Should contain some letters (not just numbers/symbols)
        if not re.search(r'[a-zA-Z]', text):
            return False
        
        return True
    
    @staticmethod
    def extract_media_references(text: str) -> List[str]:
        """
        Extract references to media files from text.
        
        Args:
            text: Text that might contain media references
            
        Returns:
            List[str]: Found media file references
        """
        # Common image/audio file extensions
        media_pattern = r'\b\w+\.(jpg|jpeg|png|gif|mp3|wav|ogg|m4a)\b'
        matches = re.findall(media_pattern, text, re.IGNORECASE)
        
        return matches
    
    @staticmethod
    def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
        """
        Truncate text to specified length with suffix.
        
        Args:
            text: Text to truncate
            max_length: Maximum length including suffix
            suffix: Suffix to add when truncating
            
        Returns:
            str: Truncated text
        """
        if not text or len(text) <= max_length:
            return text
        
        truncated_length = max_length - len(suffix)
        return text[:truncated_length] + suffix
    
    @staticmethod
    def remove_html_entities(text: str) -> str:
        """
        Remove or replace common HTML entities.
        
        Args:
            text: Text containing HTML entities
            
        Returns:
            str: Text with entities replaced
        """
        if not text:
            return ""
        
        # Common HTML entity replacements
        replacements = {
            '&quot;': '"',
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '&nbsp;': ' ',
            '&#39;': "'",
            '&ldquo;': '"',
            '&rdquo;': '"',
            '&lsquo;': "'",
            '&rsquo;': "'"
        }
        
        result = text
        for entity, replacement in replacements.items():
            result = result.replace(entity, replacement)
        
        # Handle numeric entities
        result = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), result)
        
        return result


# Convenience functions for backward compatibility
def clean_question_text(text: str) -> str:
    """Clean question text."""
    return TextProcessor.clean_question_text(text)


def clean_hint_text(text: str) -> str:
    """Clean hint text."""
    return TextProcessor.clean_hint_text(text)


def clean_description_text(text: str) -> str:
    """Clean description text.""" 
    return TextProcessor.clean_description_text(text) 