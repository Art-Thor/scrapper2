#!/usr/bin/env python3
"""
Test script for improved question type detection functionality.

This script tests the enhanced question type detection to ensure True/False questions
are properly classified instead of being misclassified as Multiple Choice.
"""

import sys
import os
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.utils.question_classifier import QuestionClassifier

def test_question_type_detection():
    """Test the improved question type detection with various examples."""
    print("🧪 Testing Enhanced Question Type Detection")
    print("=" * 60)
    
    # Initialize classifier
    classifier = QuestionClassifier()
    
    # Test cases: (question_text, options, expected_type)
    test_cases = [
        # Clear True/False cases
        ("Is Paris the capital of France?", ["True", "False"], "true_false"),
        ("Does the sun rise in the east?", ["Yes", "No"], "true_false"),
        ("Can birds fly?", ["Y", "N"], "true_false"),
        ("Was Shakespeare a playwright?", ["T", "F"], "true_false"),
        ("Are cats mammals?", ["Correct", "Incorrect"], "true_false"),
        ("Do you agree with this statement?", ["Agree", "Disagree"], "true_false"),
        
        # Case variations
        ("Is water wet?", ["true", "false"], "true_false"),
        ("Does it rain?", ["YES", "NO"], "true_false"),
        ("Will it work?", ["right", "wrong"], "true_false"),
        
        # Question patterns that suggest True/False
        ("Is it true that elephants are mammals?", ["Option A", "Option B"], "true_false"),
        ("Does this make sense to you?", ["Choice 1", "Choice 2"], "true_false"),
        ("Can you see the moon?", ["First", "Second"], "true_false"),
        
        # Clear Multiple Choice cases
        ("What is the capital of France?", ["Paris", "London", "Berlin", "Madrid"], "multiple_choice"),
        ("Which color is primary?", ["Red", "Purple", "Orange"], "multiple_choice"),
        ("What year was...", ["1990", "1991"], "multiple_choice"),  # Two options but not T/F
        
        # Sound questions
        ("Listen to this audio clip. What instrument is playing?", ["Piano", "Guitar", "Violin"], "sound"),
        ("What sound do you hear?", ["Yes", "No"], "sound"),  # Sound overrides T/F
        
        # Edge cases
        ("Choose the best option", ["Maybe", "Perhaps"], "multiple_choice"),  # Ambiguous
        ("Select one", ["Always", "Never"], "multiple_choice"),  # Could be T/F but ambiguous
        ("Pick the right answer", ["Possibly", "Definitely"], "multiple_choice"),  # Two options but not T/F
        
        # Tricky cases
        ("True or False: The sky is blue", ["True", "False"], "true_false"),
        ("Yes or No: Do you like pizza?", ["Yes", "No"], "true_false"),
        ("Correct or Incorrect: 2+2=4", ["Correct", "Incorrect"], "true_false"),
    ]
    
    # Track results
    passed = 0
    failed = 0
    
    print("\n📋 Test Results:")
    print("-" * 60)
    
    for i, (question, options, expected) in enumerate(test_cases, 1):
        try:
            result = classifier.classify(question, options)
            
            if result == expected:
                status = "✅ PASS"
                passed += 1
            else:
                status = "❌ FAIL"
                failed += 1
            
            print(f"{i:2d}. {status} | Expected: {expected:12} | Got: {result:12}")
            print(f"    Question: {question[:50]}...")
            print(f"    Options:  {options}")
            
            if result != expected:
                print(f"    ⚠️  MISMATCH: Expected {expected}, got {result}")
            
            print()
            
        except Exception as e:
            print(f"{i:2d}. ❌ ERROR | {e}")
            failed += 1
            print()
    
    # Summary
    total = len(test_cases)
    success_rate = (passed / total) * 100
    
    print("=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total Tests:   {total}")
    print(f"Passed:        {passed}")
    print(f"Failed:        {failed}")
    print(f"Success Rate:  {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🎉 Excellent! Question type detection is working well.")
    elif success_rate >= 75:
        print("👍 Good! Most questions are classified correctly.")
    else:
        print("⚠️  Needs improvement. Consider adjusting the detection logic.")
    
    return success_rate >= 75

def test_logging_output():
    """Test that logging output is working for the question type detection."""
    print("\n🧪 Testing Logging Output")
    print("=" * 40)
    
    # Set up logging to capture output
    import io
    import logging
    
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    
    # Set up logger
    logger = logging.getLogger('src.utils.question_classifier')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    
    # Test with classifier
    classifier = QuestionClassifier()
    
    # Test cases that should generate different log levels
    test_cases = [
        ("Is this true?", ["True", "False"]),  # Should log successful T/F detection
        ("What color?", ["Red", "Blue"]),      # Should log suspicious binary question
        ("Pick one", ["Maybe", "Perhaps"]),    # Should log ambiguous classification
    ]
    
    for question, options in test_cases:
        classifier.classify(question, options)
    
    # Get log output
    log_output = log_stream.getvalue()
    
    if log_output:
        print("✅ Logging is working! Sample output:")
        print("-" * 40)
        for line in log_output.split('\n')[:5]:  # Show first 5 lines
            if line.strip():
                print(f"  {line}")
        print("  ...")
    else:
        print("⚠️  No log output detected. Check logging configuration.")
    
    # Clean up
    logger.removeHandler(handler)

def test_edge_cases():
    """Test edge cases and boundary conditions."""
    print("\n🧪 Testing Edge Cases")
    print("=" * 40)
    
    classifier = QuestionClassifier()
    
    edge_cases = [
        # Empty/None cases
        ("", [], "multiple_choice"),
        ("Question?", [], "multiple_choice"),
        
        # Single option
        ("What?", ["Only option"], "multiple_choice"),
        
        # Many options
        ("Pick one", ["A", "B", "C", "D", "E", "F"], "multiple_choice"),
        
        # Case sensitivity
        ("Is it?", ["TRUE", "FALSE"], "true_false"),
        ("Does it?", ["yes", "no"], "true_false"),
        
        # Whitespace handling
        ("Test?", [" True ", " False "], "true_false"),
        ("Test?", ["  Yes  ", "  No  "], "true_false"),
        
        # Similar but not T/F
        ("Choose", ["True North", "False Positive"], "multiple_choice"),
        ("Pick", ["Yesterday", "Tomorrow"], "multiple_choice"),
    ]
    
    print("Testing edge cases:")
    for i, (question, options, expected) in enumerate(edge_cases, 1):
        try:
            result = classifier.classify(question, options)
            status = "✅" if result == expected else "❌"
            print(f"  {i:2d}. {status} {question[:20]:20} | {str(options)[:30]:30} | {result}")
        except Exception as e:
            print(f"  {i:2d}. ❌ ERROR: {e}")

def main():
    """Run all tests."""
    print("🚀 Starting Question Type Detection Tests")
    print("=" * 60)
    
    # Set up basic logging for testing
    logging.basicConfig(
        level=logging.INFO,
        format='%(name)s - %(levelname)s - %(message)s'
    )
    
    success = test_question_type_detection()
    test_logging_output()
    test_edge_cases()
    
    print("\n" + "=" * 60)
    print("🏁 FINAL SUMMARY")
    print("=" * 60)
    
    if success:
        print("✅ Question type detection improvements are working correctly!")
        print("\n📋 Next steps:")
        print("1. Run the main scraper to test with real data")
        print("2. Monitor logs for classification decisions")
        print("3. Check CSV output for proper True/False vs Multiple Choice distribution")
    else:
        print("❌ Question type detection needs further refinement.")
        print("\n🔧 Recommended actions:")
        print("1. Review failed test cases")
        print("2. Adjust detection logic in detect_question_type()")
        print("3. Add more synonyms or patterns as needed")

if __name__ == '__main__':
    main() 