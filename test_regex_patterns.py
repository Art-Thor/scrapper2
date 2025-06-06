#!/usr/bin/env python3
"""
Test script to verify the regex patterns work with actual FunTrivia text structure.
"""

import re

# Sample FunTrivia result text based on the user's example
sample_text = """
1. In 1950, Mort Walker first published a strip with bumbling, inept soldiers of various ranks stationed at the fictional Camp Swampy. The title character is a lazy, unmotivated private whose eyes are always hidden beneath whatever hat, cap, or helmet he happens to be wearing. Other characters include Killer, Zero, Plato, Cookie, Sgt. Snorkel, Lt. Fuzz, Lt. Flap, Captain Scabbard, General Halftrack, and Miss Buxley. Do you recognize this strip?
 Your Answer: [No Answer]
The correct answer was Beetle Bailey

In 2016, at the age of 92, Mort Walker was still producing his strip although with the aid of his sons as well as a few other assistants. Thus, "Beetle Bailey" is one of of the longest-running strips produced by the same creator in comic history. When Walker began the strip, it focused on Beetle's life in college at Rockview University and was based on Walker's own acquaintances at a fraternity at the University of Missouri. Within a year, however, Beetle quit college and enlisted in the Army; he has remained at Camp Swampy for all this time.

At one point in the 1950s, the strip was dropped from the "Stars and Stripes", Tokyo edition, because it was thought by some to be encouraging insubordination. This marks the only time in the strip's history that the United States Army had any problem with Walker's "Beetle Bailey".
93% of players have answered correctly.
"""

def test_extraction_patterns():
    """Test the regex patterns against sample FunTrivia text."""
    
    print("🧪 Testing FunTrivia Description Extraction Patterns")
    print("=" * 60)
    
    # Clean and normalize the text (same as in the actual function)
    text = ' '.join(sample_text.split())
    
    # Test patterns from the actual function
    patterns = [
        # Main pattern: Extract text after "The correct answer was..." until statistics
        r'The correct answer was\s+[^.]+\.\s*(.+?)(?=\d+%\s+of\s+players|I see an error|Your Answer:|Question \d+|\Z)',
        # Alternative patterns for different answer formats
        r'Correct answer was\s+[^.]+\.\s*(.+?)(?=\d+%\s+of\s+players|I see an error|Your Answer:|Question \d+|\Z)',
        r'correct answer:\s*[^.]+\.\s*(.+?)(?=\d+%\s+of\s+players|I see an error|Your Answer:|Question \d+|\Z)',
        # Pattern for when answer is in quotes
        r'The correct answer was\s+"[^"]+"\s*(.+?)(?=\d+%\s+of\s+players|I see an error|Your Answer:|Question \d+|\Z)',
        # More flexible pattern for single word answers
        r'The correct answer was\s+\w+\s*(.+?)(?=\d+%\s+of\s+players|I see an error|Your Answer:|Question \d+|\Z)',
    ]
    
    for i, pattern in enumerate(patterns, 1):
        print(f"\n🔍 Testing Pattern {i}:")
        print(f"Pattern: {pattern}")
        
        match = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if match:
            explanation = match.group(1).strip()
            explanation = re.sub(r'\s+', ' ', explanation)  # Normalize whitespace
            
            print(f"✅ MATCH FOUND!")
            print(f"Length: {len(explanation)} characters")
            print(f"Preview: {explanation[:200]}...")
            if len(explanation) > 200:
                print(f"Full text: {explanation}")
            break
        else:
            print("❌ No match")
    
    print(f"\n📊 Summary:")
    print(f"Original text length: {len(sample_text)} characters")
    print(f"Normalized text length: {len(text)} characters")

if __name__ == "__main__":
    test_extraction_patterns() 