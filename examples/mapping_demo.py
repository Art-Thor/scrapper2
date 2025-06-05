#!/usr/bin/env python3
"""
Demonstration of the centralized mapping configuration system.

This script shows how the centralized mapping system works and provides
examples of mapping operations, unmapped value handling, and configuration
management.
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from scraper.config import ScraperConfig


def demonstrate_mapping_system():
    """Demonstrate the centralized mapping system functionality."""
    
    print("🗺️  CENTRALIZED MAPPING CONFIGURATION DEMO")
    print("=" * 60)
    
    # Initialize the centralized configuration
    print("\n1. Initializing Centralized Configuration")
    print("-" * 40)
    
    try:
        config = ScraperConfig("config/mappings.json")
        print("✅ Successfully loaded mappings from config/mappings.json")
        
        # Show mapping statistics
        stats = config.get_mapping_stats()
        print("\nMapping Statistics:")
        for mapping_type, stat_data in stats.items():
            print(f"  {mapping_type}:")
            print(f"    Standard categories: {stat_data['standard_categories']}")
            print(f"    Total raw values: {stat_data['total_raw_values']}")
            print(f"    Avg values per category: {stat_data['avg_values_per_category']}")
            
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return False
    
    # Demonstrate difficulty mapping
    print("\n2. Difficulty Mapping Examples")
    print("-" * 40)
    
    test_difficulties = ["easy", "hard", "moderate", "unknown_difficulty"]
    for difficulty in test_difficulties:
        # MAPPING LOOKUP: Using centralized configuration for difficulty mapping
        mapped = config.map_difficulty(difficulty)
        print(f"  '{difficulty}' → '{mapped}'")
    
    # Demonstrate domain mapping  
    print("\n3. Domain Mapping Examples")
    print("-" * 40)
    
    test_domains = ["science", "entertainment", "sports", "unknown_domain"]
    for domain in test_domains:
        # MAPPING LOOKUP: Using centralized configuration for domain mapping
        mapped = config.map_domain(domain)
        print(f"  '{domain}' → '{mapped}'")
    
    # Demonstrate topic mapping
    print("\n4. Topic Mapping Examples")
    print("-" * 40)
    
    test_topics = ["music", "animals", "movies", "unknown_topic"]
    for topic in test_topics:
        # MAPPING LOOKUP: Using centralized configuration for topic mapping  
        mapped = config.map_topic(topic)
        print(f"  '{topic}' → '{mapped}'")
    
    # Show unmapped values
    print("\n5. Unmapped Values Detection")
    print("-" * 40)
    
    unmapped = config.get_unmapped_values()
    if any(unmapped.values()):
        print("Values that were not found in mappings:")
        for mapping_type, values in unmapped.items():
            if values:
                print(f"  {mapping_type}: {', '.join(sorted(values))}")
    else:
        print("No unmapped values detected in this demo.")
    
    # Demonstrate configuration validation
    print("\n6. Configuration Validation")
    print("-" * 40)
    
    validation_results = config.validate_mappings()
    overall_valid = all(validation_results.values())
    
    print(f"Overall validation: {'✅ PASSED' if overall_valid else '❌ FAILED'}")
    for mapping_type, is_valid in validation_results.items():
        status = "✅ Valid" if is_valid else "❌ Invalid"
        print(f"  {mapping_type}: {status}")
    
    # Show how to handle missing mappings
    print("\n7. Handling Missing Mappings")
    print("-" * 40)
    
    print("When a value is not found in mappings:")
    print("  1. A warning is logged")
    print("  2. The original value is returned as fallback")
    print("  3. The value is tracked for later review")
    print("  4. Users can identify missing mappings via get_unmapped_values()")
    
    # Show configuration file structure
    print("\n8. Configuration File Structure")
    print("-" * 40)
    
    print("The mappings are defined in config/mappings.json with structure:")
    print("""{
    "difficulty_mapping": {
        "Easy": ["easy", "beginner", "simple", ...],
        "Normal": ["normal", "medium", "average", ...],
        "Hard": ["hard", "difficult", "challenging", ...]
    },
    "domain_mapping": {
        "Nature": ["nature", "animals", "wildlife", ...],
        "Science": ["science", "physics", "chemistry", ...],
        ...
    },
    "topic_mapping": {
        "General": ["general", "mixed", "various", ...],
        "Animals": ["animals", "pets", "mammals", ...],
        ...
    }
}""")
    
    print("\n9. Benefits of Centralized Mapping")
    print("-" * 40)
    
    benefits = [
        "✅ Single source of truth for all mappings",
        "✅ Consistent mapping behavior across all scrapers", 
        "✅ Easy to update mappings without code changes",
        "✅ Automatic fallback to original values",
        "✅ Detection and reporting of unmapped values",
        "✅ Validation of mapping configuration",
        "✅ No hardcoded mappings in scraper logic"
    ]
    
    for benefit in benefits:
        print(f"  {benefit}")
    
    print("\n" + "=" * 60)
    print("Demo completed! The centralized mapping system provides")
    print("consistent, maintainable, and transparent value mapping.")
    print("=" * 60)
    
    return True


def show_usage_examples():
    """Show code examples of how to use the centralized mapping system."""
    
    print("\n🔧 USAGE EXAMPLES")
    print("=" * 60)
    
    print("\nIn your scraper code:")
    print("""
# 1. Initialize centralized configuration
from scraper.config import ScraperConfig
config = ScraperConfig("config/mappings.json")

# 2. Use mapping methods with clear comments
# MAPPING LOOKUP: Using centralized configuration for difficulty mapping
mapped_difficulty = config.map_difficulty(raw_difficulty)

# MAPPING LOOKUP: Using centralized configuration for domain mapping  
mapped_domain = config.map_domain(raw_domain)

# MAPPING LOOKUP: Using centralized configuration for topic mapping
mapped_topic = config.map_topic(raw_topic)

# 3. Check for unmapped values after scraping
unmapped = config.get_unmapped_values()
if unmapped['difficulty']:
    print(f"Unmapped difficulties: {unmapped['difficulty']}")

# 4. Get mapping statistics
stats = config.get_mapping_stats()
print(f"Total difficulty mappings: {stats['difficulty_mapping']['total_raw_values']}")

# 5. Validate configuration
validation = config.validate_mappings()
if not all(validation.values()):
    print("Configuration validation failed!")
    """)
    
    print("\nKey features:")
    print("  • No hardcoded mappings in scraper logic")
    print("  • Automatic fallback to original values when mapping not found")
    print("  • Clear logging and warning for unmapped values")
    print("  • Easy identification of missing mappings for config updates")


if __name__ == "__main__":
    print("Starting centralized mapping configuration demonstration...")
    
    if demonstrate_mapping_system():
        show_usage_examples()
        print("\n✅ Demo completed successfully!")
    else:
        print("\n❌ Demo failed - check configuration file")
        sys.exit(1) 