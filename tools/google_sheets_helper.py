#!/usr/bin/env python3
"""
Google Sheets Helper Tool for FunTrivia Scraper

This tool helps you set up and test Google Sheets integration with step-by-step guidance.

Usage:
  python tools/google_sheets_helper.py --help
  python tools/google_sheets_helper.py --setup-guide
  python tools/google_sheets_helper.py --test-connection
  python tools/google_sheets_helper.py --show-examples
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from utils.sheets import test_google_sheets_setup, print_setup_instructions
except ImportError as e:
    print(f"❌ Error importing Google Sheets modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)


def show_usage_examples():
    """Show comprehensive usage examples for Google Sheets integration."""
    examples = """
📊 GOOGLE SHEETS USAGE EXAMPLES

═══════════════════════════════════════════════════════════════════════════════

🔍 TESTING CONNECTION (No Scraping)
═══════════════════════════════════════════════════════════════════════════════

Test your Google Sheets setup before running the scraper:

  python src/main.py --sheets-test-only \\
    --sheets-credentials credentials/service-account.json \\
    --sheets-id 1abc123def456ghi789jkl

This will:
• Validate your credentials file
• Test authentication with Google Sheets API
• Check access to your spreadsheet
• Display spreadsheet information
• Exit without scraping

═══════════════════════════════════════════════════════════════════════════════

🚀 SCRAPING WITH GOOGLE SHEETS UPLOAD
═══════════════════════════════════════════════════════════════════════════════

Method 1: Command Line (Recommended)
────────────────────────────────────────────────────────────────────────────────

  python src/main.py --upload-to-sheets \\
    --sheets-credentials credentials/service-account.json \\
    --sheets-id 1abc123def456ghi789jkl \\
    --max-questions 100

Benefits:
• Explicit control over when uploads happen
• Easy to see what credentials are being used
• Overrides any config file settings

Method 2: Configuration File
────────────────────────────────────────────────────────────────────────────────

Edit config/settings.json:
```json
{
  "google_sheets": {
    "enabled": true,
    "credentials_file": "credentials/service-account.json",
    "spreadsheet_id": "1abc123def456ghi789jkl"
  }
}
```

Then run:
  python src/main.py --max-questions 100

═══════════════════════════════════════════════════════════════════════════════

🛑 DISABLING GOOGLE SHEETS UPLOAD
═══════════════════════════════════════════════════════════════════════════════

Default Behavior:
  python src/main.py --max-questions 100
  # Google Sheets upload is DISABLED by default

Explicit Disable (overrides config file):
  python src/main.py --no-sheets-upload --max-questions 100

═══════════════════════════════════════════════════════════════════════════════

🔧 COMMON WORKFLOWS
═══════════════════════════════════════════════════════════════════════════════

1. First Time Setup:
   python tools/google_sheets_helper.py --setup-guide
   python src/main.py --sheets-test-only --sheets-credentials ... --sheets-id ...
   python src/main.py --upload-to-sheets --sheets-credentials ... --sheets-id ... --max-questions 10

2. Regular Usage:
   python src/main.py --upload-to-sheets --sheets-credentials ... --sheets-id ... --max-questions 100

3. Debugging Issues:
   python src/main.py --sheets-test-only --sheets-credentials ... --sheets-id ...
   python tools/google_sheets_helper.py --setup-guide

4. Development/Testing (no upload):
   python src/main.py --no-sheets-upload --max-questions 50

═══════════════════════════════════════════════════════════════════════════════

🔐 SECURITY CONSIDERATIONS
═══════════════════════════════════════════════════════════════════════════════

✅ DO:
• Keep credentials files secure and private
• Add credentials/ to .gitignore
• Use minimum required permissions
• Regularly rotate service account keys
• Test connection before large scraping runs

❌ DON'T:
• Commit credentials to version control
• Share credentials files publicly
• Use overly broad permissions
• Leave old credentials active

═══════════════════════════════════════════════════════════════════════════════

📝 SPREADSHEET STRUCTURE
═══════════════════════════════════════════════════════════════════════════════

The scraper will create/update these worksheets:
• "Multiple Choice" - Questions with 4 options and optional images
• "True/False" - Questions with 2 options
• "Sound" - Questions with 4 options and audio files

Each worksheet contains:
Key, Domain, Topic, Difficulty, Question, Option1, Option2, [Option3, Option4], 
CorrectAnswer, Hint, Description, [ImagePath/AudioPath]

═══════════════════════════════════════════════════════════════════════════════
"""
    print(examples)


def interactive_test():
    """Interactive Google Sheets connection testing."""
    print("🔍 Interactive Google Sheets Connection Test")
    print("═" * 60)
    print()
    
    # Get credentials file
    print("Step 1: Locate your credentials file")
    default_creds = "credentials/service-account.json"
    
    if os.path.exists(default_creds):
        print(f"✅ Found default credentials file: {default_creds}")
        use_default = input("Use this file? [Y/n]: ").strip().lower()
        if use_default in ['', 'y', 'yes']:
            credentials_file = default_creds
        else:
            credentials_file = input("Enter path to credentials file: ").strip()
    else:
        print(f"⚠️ Default credentials file not found: {default_creds}")
        credentials_file = input("Enter path to credentials file: ").strip()
    
    if not os.path.exists(credentials_file):
        print(f"❌ Credentials file not found: {credentials_file}")
        print("Please check the path and try again.")
        return False
    
    # Get spreadsheet ID
    print("\nStep 2: Enter your Google Spreadsheet ID")
    print("(Found in the URL: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit)")
    spreadsheet_id = input("Spreadsheet ID: ").strip()
    
    if not spreadsheet_id:
        print("❌ Spreadsheet ID is required")
        return False
    
    # Run test
    print("\nStep 3: Testing connection...")
    print("─" * 40)
    
    success = test_google_sheets_setup(credentials_file, spreadsheet_id)
    
    if success:
        print("\n🎉 Success! Your Google Sheets integration is ready.")
        print("\nNext steps:")
        print(f"  python src/main.py --upload-to-sheets \\")
        print(f"    --sheets-credentials {credentials_file} \\")
        print(f"    --sheets-id {spreadsheet_id} \\")
        print(f"    --max-questions 10")
    else:
        print("\n❌ Connection test failed. Please check the setup instructions.")
        print("\nFor detailed setup help, run:")
        print("  python tools/google_sheets_helper.py --setup-guide")
    
    return success


def check_environment():
    """Check if the environment is properly set up for Google Sheets."""
    print("🔍 Checking Google Sheets Environment")
    print("─" * 40)
    
    issues = []
    
    # Check Python dependencies
    try:
        import gspread
        print("✅ gspread library installed")
    except ImportError:
        issues.append("gspread library not installed")
        print("❌ gspread library not installed")
    
    try:
        import oauth2client
        print("✅ oauth2client library installed")
    except ImportError:
        issues.append("oauth2client library not installed")
        print("❌ oauth2client library not installed")
    
    # Check directory structure
    if os.path.exists("credentials"):
        print("✅ credentials/ directory exists")
    else:
        issues.append("credentials/ directory missing")
        print("❌ credentials/ directory missing")
    
    # Check for common credential files
    common_paths = [
        "credentials/service-account.json",
        "credentials/google-credentials.json",
        "credentials/sheets-credentials.json"
    ]
    
    found_creds = False
    for path in common_paths:
        if os.path.exists(path):
            print(f"✅ Found credentials file: {path}")
            found_creds = True
            break
    
    if not found_creds:
        issues.append("No credentials file found in common locations")
        print("⚠️ No credentials file found in common locations")
    
    # Check config file
    config_path = "config/settings.json"
    if os.path.exists(config_path):
        print("✅ Configuration file exists")
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            gs_config = config.get('google_sheets', {})
            if gs_config.get('enabled', False):
                print("⚠️ Google Sheets enabled in config (use --no-sheets-upload to override)")
            else:
                print("✅ Google Sheets disabled in config (default)")
        except Exception as e:
            issues.append(f"Error reading config file: {e}")
            print(f"❌ Error reading config file: {e}")
    else:
        issues.append("Configuration file missing")
        print("❌ Configuration file missing")
    
    # Summary
    if issues:
        print(f"\n⚠️ Found {len(issues)} issues:")
        for issue in issues:
            print(f"  • {issue}")
        print("\nTo fix these issues:")
        print("  pip install gspread oauth2client")
        print("  mkdir -p credentials")
        print("  python tools/google_sheets_helper.py --setup-guide")
        return False
    else:
        print("\n✅ Environment looks good for Google Sheets integration!")
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Google Sheets Helper for FunTrivia Scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/google_sheets_helper.py --setup-guide
  python tools/google_sheets_helper.py --test-connection
  python tools/google_sheets_helper.py --show-examples
  python tools/google_sheets_helper.py --check-env
        """
    )
    
    parser.add_argument('--setup-guide', action='store_true',
                       help='Show detailed setup instructions')
    parser.add_argument('--test-connection', action='store_true',
                       help='Interactive connection testing')
    parser.add_argument('--show-examples', action='store_true',
                       help='Show usage examples')
    parser.add_argument('--check-env', action='store_true',
                       help='Check environment setup')
    parser.add_argument('--credentials', type=str,
                       help='Path to credentials file for testing')
    parser.add_argument('--spreadsheet-id', type=str,
                       help='Spreadsheet ID for testing')
    
    args = parser.parse_args()
    
    if args.setup_guide:
        print_setup_instructions()
        return 0
    
    elif args.show_examples:
        show_usage_examples()
        return 0
    
    elif args.check_env:
        success = check_environment()
        return 0 if success else 1
    
    elif args.test_connection:
        if args.credentials and args.spreadsheet_id:
            # Non-interactive test
            success = test_google_sheets_setup(args.credentials, args.spreadsheet_id)
            return 0 if success else 1
        else:
            # Interactive test
            success = interactive_test()
            return 0 if success else 1
    
    else:
        # Default: show help and basic info
        print("🔧 Google Sheets Helper Tool")
        print("═" * 50)
        print()
        print("This tool helps you set up and test Google Sheets integration.")
        print()
        print("Available options:")
        print("  --setup-guide     Show detailed setup instructions")
        print("  --test-connection Interactive connection testing")
        print("  --show-examples   Show usage examples")
        print("  --check-env       Check environment setup")
        print()
        print("Quick start:")
        print("  python tools/google_sheets_helper.py --setup-guide")
        print("  python tools/google_sheets_helper.py --test-connection")
        print()
        
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1) 