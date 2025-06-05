#!/usr/bin/env python3
"""
Demonstration of the media download and management system.

This script shows how the MediaHandler works with proper localization keys,
filename handling, and directory structure management.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add the src directory to the path
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from scraper.media import MediaHandler, MediaReference


def demonstrate_media_system():
    """Demonstrate the media handling system functionality."""
    
    print("🎥 MEDIA DOWNLOAD AND MANAGEMENT DEMO")
    print("=" * 60)
    
    # Sample configuration
    config = {
        'storage': {
            'images_dir': 'assets/images',
            'audio_dir': 'assets/audio'
        }
    }
    
    # Initialize MediaHandler
    print("\n1. Initializing MediaHandler")
    print("-" * 40)
    
    try:
        media_handler = MediaHandler(config)
        print("✅ MediaHandler initialized successfully")
        print(f"   Images directory: {config['storage']['images_dir']}")
        print(f"   Audio directory: {config['storage']['audio_dir']}")
    except Exception as e:
        print(f"❌ Failed to initialize MediaHandler: {e}")
        return False
    
    # Demonstrate filename generation
    print("\n2. Localization Key-Based Filename Generation")
    print("-" * 40)
    
    sample_urls = [
        "https://example.com/audio/sample.mp3",
        "https://example.com/images/photo.jpg",
        "https://example.com/media/sound.wav",
        "https://example.com/files/image.png"
    ]
    
    sample_question_ids = [
        "Question_Sound_Parsed_Culture_Easy_0001",
        "Question_MQ_Parsed_Science_Normal_0002", 
        "Question_Sound_Parsed_Nature_Hard_0003",
        "Question_MQ_Parsed_History_Easy_0004"
    ]
    
    print("Sample filename generation:")
    for i, (url, question_id) in enumerate(zip(sample_urls, sample_question_ids)):
        media_type = 'audio' if 'audio' in url or 'sound' in url else 'image'
        filename = media_handler.get_media_filename(question_id, media_type, url)
        filepath = media_handler.get_media_filepath(question_id, media_type, url)
        csv_ref = media_handler.get_csv_reference(question_id, media_type, url)
        
        print(f"  {i+1}. {media_type.upper()}")
        print(f"     Question ID: {question_id}")
        print(f"     Source URL: {url}")
        print(f"     Filename: {filename}")
        print(f"     Full Path: {filepath}")
        print(f"     CSV Reference: {csv_ref}")
        print()
    
    # Demonstrate MediaReference helper
    print("\n3. MediaReference Helper Functions")
    print("-" * 40)
    
    sample_question_data = [
        {
            'type': 'sound',
            'audioUrl': 'https://example.com/audio/sample.mp3',
            'questionNumber': '1'
        },
        {
            'type': 'multiple_choice', 
            'imageUrl': 'https://example.com/images/photo.jpg',
            'questionNumber': '2'
        }
    ]
    
    for question_data in sample_question_data:
        media_url = MediaReference.extract_media_path(question_data)
        media_type = MediaReference.get_media_type_from_question(question_data['type'])
        
        print(f"Question Type: {question_data['type']}")
        print(f"  Extracted Media URL: {media_url}")
        print(f"  Determined Media Type: {media_type}")
        
        # Simulate CSV formatting
        formatted_question = {
            'Key': f"Question_{question_data['type']}_Sample",
            'AudioPath': '',
            'ImagePath': ''
        }
        
        if media_url:
            filename = "sample_filename.mp3" if media_type == 'audio' else "sample_filename.jpg"
            MediaReference.set_csv_media_reference(formatted_question, question_data['type'], filename)
            
            print(f"  CSV Fields Set:")
            if formatted_question.get('AudioPath'):
                print(f"    AudioPath: {formatted_question['AudioPath']}")
            if formatted_question.get('ImagePath'):
                print(f"    ImagePath: {formatted_question['ImagePath']}")
        print()
    
    # Show benefits
    print("\n4. Key Benefits of the Media System")
    print("-" * 40)
    
    benefits = [
        "✅ Filenames match question localization keys exactly",
        "✅ Only filenames (not paths) written to CSV columns",
        "✅ Proper directory structure (assets/images/, assets/audio/)",
        "✅ Automatic file extension handling based on media type",
        "✅ Retry logic for robust downloads",
        "✅ Media file validation and statistics",
        "✅ Cleanup of temporary files",
        "✅ Consistent media reference handling"
    ]
    
    for benefit in benefits:
        print(f"  {benefit}")
    
    # Show example CSV output
    print("\n5. Example CSV Output")
    print("-" * 40)
    
    print("Multiple Choice Question CSV:")
    print("Key,Domain,Topic,Difficulty,Question,Option1,Option2,Option3,Option4,CorrectAnswer,Hint,Description,ImagePath")
    print("Question_MQ_Parsed_Culture_Easy_0001,Culture,Movies,Easy,\"What movie?\",A,B,C,D,A,Hint,Desc,Question_MQ_Parsed_Culture_Easy_0001.jpg")
    
    print("\nSound Question CSV:")
    print("Key,Domain,Topic,Difficulty,Question,Option1,Option2,Option3,Option4,CorrectAnswer,Hint,Description,AudioPath")
    print("Question_Sound_Parsed_Music_Normal_0001,Culture,Music,Normal,\"What song?\",A,B,C,D,A,Hint,Desc,Question_Sound_Parsed_Music_Normal_0001.mp3")
    
    print("\n6. File System Structure")
    print("-" * 40)
    
    print("""
project/
├── assets/
│   ├── images/
│   │   ├── Question_MQ_Parsed_Culture_Easy_0001.jpg
│   │   ├── Question_MQ_Parsed_Science_Normal_0002.png
│   │   └── ...
│   └── audio/
│       ├── Question_Sound_Parsed_Music_Normal_0001.mp3
│       ├── Question_Sound_Parsed_Nature_Hard_0002.wav
│       └── ...
└── output/
    ├── multiple_choice.csv  (ImagePath column contains just filenames)
    ├── true_false.csv
    └── sound.csv           (AudioPath column contains just filenames)
    """)
    
    print("\n" + "=" * 60)
    print("Demo completed! The media system provides:")
    print("• Consistent filename management using localization keys")
    print("• Proper CSV references (filename only, no paths)")
    print("• Organized directory structure for different media types")
    print("• Robust error handling and validation")
    print("=" * 60)
    
    return True


async def demonstrate_download_process():
    """Show how the download process would work (without actual downloads)."""
    
    print("\n🔄 DOWNLOAD PROCESS DEMONSTRATION")
    print("=" * 60)
    
    config = {
        'storage': {
            'images_dir': 'assets/images',
            'audio_dir': 'assets/audio'
        }
    }
    
    media_handler = MediaHandler(config)
    
    # Sample download scenarios
    scenarios = [
        {
            'url': 'https://example.com/audio/sample.mp3',
            'question_id': 'Question_Sound_Parsed_Music_Easy_0001',
            'media_type': 'audio'
        },
        {
            'url': 'https://example.com/images/photo.jpg', 
            'question_id': 'Question_MQ_Parsed_Science_Normal_0002',
            'media_type': 'image'
        }
    ]
    
    print("Download scenarios (simulated):")
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{i}. {scenario['media_type'].upper()} Download:")
        print(f"   Source URL: {scenario['url']}")
        print(f"   Question ID: {scenario['question_id']}")
        
        # Show what would happen
        expected_filename = media_handler.get_csv_reference(
            scenario['question_id'], 
            scenario['media_type'], 
            scenario['url']
        )
        expected_filepath = media_handler.get_media_filepath(
            scenario['question_id'],
            scenario['media_type'], 
            scenario['url']
        )
        
        print(f"   → Would save to: {expected_filepath}")
        print(f"   → CSV would contain: {expected_filename}")
        
        # Note: Actual download would be:
        # filename = await media_handler.download_media(
        #     url=scenario['url'],
        #     question_id=scenario['question_id'],
        #     media_type=scenario['media_type']
        # )


if __name__ == "__main__":
    print("Starting media download and management demonstration...")
    
    if demonstrate_media_system():
        asyncio.run(demonstrate_download_process())
        print("\n✅ Demo completed successfully!")
    else:
        print("\n❌ Demo failed")
        sys.exit(1) 