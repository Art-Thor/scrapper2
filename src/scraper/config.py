"""
Centralized configuration and mapping handler for the FunTrivia scraper.

This module handles all difficulty, domain, and topic mappings to ensure
consistency across the codebase and provide proper fallback behavior.
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path


class ScraperConfig:
    """
    Centralized configuration and mapping handler.
    
    Loads and manages all difficulty, domain, and topic mappings from the
    configuration file, providing a unified interface for mapping operations.
    """
    
    def __init__(self, mappings_file: str = "config/mappings.json"):
        """
        Initialize the configuration handler.
        
        Args:
            mappings_file: Path to the JSON file containing all mapping definitions
        """
        self.logger = logging.getLogger(__name__)
        self.mappings_file = mappings_file
        self.mappings = self._load_mappings()
        
        # Store original unmapped values for fallback behavior
        self._unmapped_values = {
            'difficulty': set(),
            'domain': set(), 
            'topic': set()
        }
    
    def _load_mappings(self) -> Dict[str, Any]:
        """
        Load all mapping dictionaries from the configuration file.
        
        Returns:
            Dictionary containing difficulty_mapping, domain_mapping, and topic_mapping
            
        Raises:
            FileNotFoundError: If mappings file doesn't exist
            json.JSONDecodeError: If mappings file is invalid JSON
        """
        try:
            mappings_path = Path(self.mappings_file)
            if not mappings_path.exists():
                raise FileNotFoundError(f"Mappings file not found: {self.mappings_file}")
                
            with open(mappings_path, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            
            # Validate required mapping sections exist
            required_sections = ['difficulty_mapping', 'domain_mapping', 'topic_mapping']
            for section in required_sections:
                if section not in mappings:
                    raise KeyError(f"Required mapping section '{section}' not found in {self.mappings_file}")
            
            self.logger.info(f"Successfully loaded mappings from {self.mappings_file}")
            self.logger.debug(f"Loaded {len(mappings['difficulty_mapping'])} difficulty mappings")
            self.logger.debug(f"Loaded {len(mappings['domain_mapping'])} domain mappings") 
            self.logger.debug(f"Loaded {len(mappings['topic_mapping'])} topic mappings")
            
            return mappings
            
        except Exception as e:
            self.logger.error(f"Failed to load mappings from {self.mappings_file}: {e}")
            raise
    
    def map_difficulty(self, raw_difficulty: str) -> str:
        """
        Map a raw difficulty value from FunTrivia to a standardized difficulty level.
        
        Performs case-insensitive lookup in the difficulty_mapping configuration.
        If no mapping is found, logs a warning and returns the original value as fallback.
        
        Args:
            raw_difficulty: Raw difficulty value from FunTrivia (e.g., "easy", "difficult")
            
        Returns:
            Standardized difficulty level (e.g., "Easy", "Normal", "Hard") or original value
        """
        # Mapping lookup - check all standardized difficulties against raw values
        for std_difficulty, raw_values in self.mappings['difficulty_mapping'].items():
            if raw_difficulty.lower() in [v.lower() for v in raw_values]:
                self.logger.debug(f"Mapped difficulty '{raw_difficulty}' -> '{std_difficulty}'")
                return std_difficulty
        
        # Fallback behavior - log warning and use original value
        if raw_difficulty not in self._unmapped_values['difficulty']:
            self.logger.warning(f"Unknown difficulty level: '{raw_difficulty}'. "
                              f"Using original value as fallback. "
                              f"Consider adding to difficulty_mapping in {self.mappings_file}")
            self._unmapped_values['difficulty'].add(raw_difficulty)
        
        return raw_difficulty
    
    def map_domain(self, raw_domain: str) -> str:
        """
        Map a raw domain value from FunTrivia to a standardized domain category.
        
        Performs case-insensitive lookup in the domain_mapping configuration.
        If no mapping is found, logs a warning and returns the original value as fallback.
        
        Args:
            raw_domain: Raw domain value from FunTrivia (e.g., "entertainment", "science")
            
        Returns:
            Standardized domain category (e.g., "Culture", "Science", "Nature") or original value
        """
        # Mapping lookup - check all standardized domains against raw values
        for std_domain, raw_values in self.mappings['domain_mapping'].items():
            if raw_domain.lower() in [v.lower() for v in raw_values]:
                self.logger.debug(f"Mapped domain '{raw_domain}' -> '{std_domain}'")
                return std_domain
        
        # Fallback behavior - log warning and use original value
        if raw_domain not in self._unmapped_values['domain']:
            self.logger.warning(f"Unknown domain: '{raw_domain}'. "
                              f"Using original value as fallback. "
                              f"Consider adding to domain_mapping in {self.mappings_file}")
            self._unmapped_values['domain'].add(raw_domain)
        
        return raw_domain
    
    def map_topic(self, raw_topic: str) -> str:
        """
        Map a raw topic value from FunTrivia to a standardized topic category.
        
        Performs case-insensitive lookup in the topic_mapping configuration.
        If no mapping is found, logs a warning and returns the original value as fallback.
        
        Args:
            raw_topic: Raw topic value from FunTrivia (e.g., "movie trivia", "animals")
            
        Returns:
            Standardized topic category (e.g., "Movies", "Animals", "General") or original value
        """
        # Mapping lookup - check all standardized topics against raw values
        for std_topic, raw_values in self.mappings['topic_mapping'].items():
            if raw_topic.lower() in [v.lower() for v in raw_values]:
                self.logger.debug(f"Mapped topic '{raw_topic}' -> '{std_topic}'")
                return std_topic
        
        # Fallback behavior - log warning and use original value
        if raw_topic not in self._unmapped_values['topic']:
            self.logger.warning(f"Unknown topic: '{raw_topic}'. "
                              f"Using original value as fallback. "
                              f"Consider adding to topic_mapping in {self.mappings_file}")
            self._unmapped_values['topic'].add(raw_topic)
        
        return raw_topic
    
    def get_unmapped_values(self) -> Dict[str, set]:
        """
        Get all values that have been encountered but not found in mappings.
        
        Useful for identifying missing mappings that should be added to the config file.
        
        Returns:
            Dictionary with 'difficulty', 'domain', and 'topic' keys containing sets of unmapped values
        """
        return {
            'difficulty': self._unmapped_values['difficulty'].copy(),
            'domain': self._unmapped_values['domain'].copy(),
            'topic': self._unmapped_values['topic'].copy()
        }
    
    def reload_mappings(self) -> None:
        """
        Reload mappings from the configuration file.
        
        Useful for picking up changes to the mappings file without restarting the application.
        """
        self.logger.info("Reloading mappings from configuration file")
        self.mappings = self._load_mappings()
        
        # Clear unmapped values cache to re-evaluate with new mappings
        self._unmapped_values = {
            'difficulty': set(),
            'domain': set(),
            'topic': set()
        }
    
    def validate_mappings(self) -> Dict[str, bool]:
        """
        Validate the loaded mappings for common issues.
        
        Returns:
            Dictionary indicating validation status for each mapping type
        """
        validation_results = {
            'difficulty_mapping': True,
            'domain_mapping': True,
            'topic_mapping': True
        }
        
        # Check for empty mappings
        for mapping_type in ['difficulty_mapping', 'domain_mapping', 'topic_mapping']:
            if not self.mappings.get(mapping_type):
                self.logger.error(f"Empty or missing {mapping_type}")
                validation_results[mapping_type] = False
            elif not isinstance(self.mappings[mapping_type], dict):
                self.logger.error(f"{mapping_type} is not a dictionary")
                validation_results[mapping_type] = False
        
        # Check for duplicate values across different standard categories
        for mapping_type in ['difficulty_mapping', 'domain_mapping', 'topic_mapping']:
            if validation_results[mapping_type]:
                all_values = []
                for std_key, raw_values in self.mappings[mapping_type].items():
                    if isinstance(raw_values, list):
                        all_values.extend([v.lower() for v in raw_values])
                    else:
                        self.logger.warning(f"Non-list value in {mapping_type}[{std_key}]: {raw_values}")
                
                duplicates = set([v for v in all_values if all_values.count(v) > 1])
                if duplicates:
                    self.logger.warning(f"Duplicate values in {mapping_type}: {duplicates}")
        
        return validation_results
    
    def get_mapping_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get statistics about the loaded mappings.
        
        Returns:
            Dictionary with counts and statistics for each mapping type
        """
        stats = {}
        
        for mapping_type in ['difficulty_mapping', 'domain_mapping', 'topic_mapping']:
            mapping = self.mappings.get(mapping_type, {})
            total_raw_values = sum(len(raw_values) for raw_values in mapping.values() if isinstance(raw_values, list))
            
            stats[mapping_type] = {
                'standard_categories': len(mapping),
                'total_raw_values': total_raw_values,
                'avg_values_per_category': round(total_raw_values / len(mapping), 1) if mapping else 0
            }
        
        return stats 