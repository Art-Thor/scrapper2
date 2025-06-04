#!/usr/bin/env python3
"""
Setup script for FunTrivia Scraper
Creates necessary directories and validates environment
"""

import os
import sys
import json
import subprocess
from pathlib import Path

def create_directories():
    """Create all necessary directories for the scraper."""
    directories = [
        "output",
        "assets",
        "assets/images", 
        "assets/audio",
        "logs",
        "credentials"
    ]
    
    print("Creating directory structure...")
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Created: {directory}")

def validate_config_files():
    """Validate and create default config files if missing."""
    config_files = {
        "config/settings.json": {
            "scraper": {
                "base_url": "https://www.funtrivia.com",
                "max_questions_per_run": 100,
                "concurrency": 3,
                "rate_limit": {
                    "requests_per_minute": 30
                }
            },
            "storage": {
                "output_dir": "output",
                "images_dir": "assets/images",
                "audio_dir": "assets/audio",
                "csv_files": {
                    "multiple_choice": "multiple_choice.csv",
                    "true_false": "true_false.csv",
                    "sound": "sound.csv"
                }
            },
            "google_sheets": {
                "enabled": False,
                "credentials_file": "credentials/service-account.json",
                "spreadsheet_id": ""
            },
            "logging": {
                "level": "INFO",
                "file": "logs/scraper.log"
            }
        }
    }
    
    print("\nValidating configuration files...")
    for file_path, default_config in config_files.items():
        config_path = Path(file_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not config_path.exists():
            with open(config_path, 'w') as f:
                json.dump(default_config, f, indent=2)
            print(f"  ✓ Created default: {file_path}")
        else:
            try:
                with open(config_path, 'r') as f:
                    json.load(f)
                print(f"  ✓ Validated: {file_path}")
            except json.JSONDecodeError as e:
                print(f"  ❌ Invalid JSON in {file_path}: {e}")
                return False
    
    return True

def check_dependencies():
    """Check if all required dependencies are installed."""
    print("\nChecking dependencies...")
    
    required_packages = [
        "playwright",
        "pandas", 
        "gspread",
        "oauth2client",
        "aiohttp",
        "tenacity",
        "bs4"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✓ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"  ❌ {package} - Missing")
    
    if missing_packages:
        print(f"\nMissing packages: {', '.join(missing_packages)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    return True

def check_playwright_browsers():
    """Check if Playwright browsers are installed."""
    print("\nChecking Playwright browsers...")
    
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium.launch(); print('OK')"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("  ✓ Playwright browsers installed")
            return True
        else:
            print("  ❌ Playwright browsers not installed")
            print("Install with: playwright install chromium")
            return False
            
    except subprocess.TimeoutExpired:
        print("  ❌ Playwright browser check timed out")
        return False
    except Exception as e:
        print(f"  ❌ Error checking Playwright: {e}")
        return False

def create_env_example():
    """Create an example environment file."""
    env_content = """# FunTrivia Scraper Environment Variables

# Google Sheets Configuration (optional)
GOOGLE_SHEETS_ENABLED=false
GOOGLE_SPREADSHEET_ID=your_spreadsheet_id_here

# Scraper Configuration
MAX_QUESTIONS=100
CONCURRENCY=3
RATE_LIMIT_PER_MINUTE=30

# Logging
LOG_LEVEL=INFO
"""
    
    env_path = Path(".env.example")
    if not env_path.exists():
        with open(env_path, 'w') as f:
            f.write(env_content)
        print("  ✓ Created: .env.example")

def main():
    """Main setup function."""
    print("🚀 FunTrivia Scraper Setup")
    print("=" * 40)
    
    # Create directories
    create_directories()
    
    # Validate config files
    if not validate_config_files():
        print("\n❌ Setup failed: Configuration file errors")
        return False
    
    # Create env example
    create_env_example()
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Setup failed: Missing dependencies")
        return False
    
    # Check Playwright browsers
    playwright_ok = check_playwright_browsers()
    
    print("\n" + "=" * 40)
    print("✅ Setup completed successfully!")
    print("\nNext steps:")
    print("1. Install missing dependencies: pip install -r requirements.txt")
    if not playwright_ok:
        print("2. Install Playwright browsers: playwright install chromium")
    print("3. Configure Google Sheets (optional): edit config/settings.json")
    print("4. Run the scraper: python src/main.py --max-questions 10")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 