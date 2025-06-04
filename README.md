# FunTrivia Quiz Scraper

A comprehensive web scraper for extracting quiz questions from FunTrivia.com with support for multiple question types, automatic media downloads, Google Sheets integration, and advanced concurrency control.

## 🚀 Enhanced Features

- **Multiple Question Types**: Supports multiple choice, true/false, and sound-based questions with automatic detection
- **Smart Answer Detection**: Automatically identifies correct answers and extracts hints/explanations from results pages
- **Advanced Media Handling**: Downloads and manages images and audio files with standardized localization keys
- **Configurable Concurrency**: Advanced controls for concurrent scrapers with safety warnings and validation
- **Enhanced Rate Limiting**: Configurable min/max delays between requests with randomization for detection avoidance
- **Google Sheets Integration**: Automatic upload to Google Sheets with comprehensive error handling (disabled by default)
- **Comprehensive Logging**: Detailed logging to both file and console with rotating log files and error tracking
- **Robust Error Handling**: Individual quiz/question failures don't stop the entire process, with full stack traces
- **CSV Export**: Standardized CSV output matching specific template formats with proper validation
- **Docker Support**: Easy deployment with containerization and volume mounting
- **Persistent Indexing**: Maintains question numbering across multiple runs with proper localization keys
- **Append Mode**: Adds new questions to existing CSV files without overwriting existing data
- **Performance Monitoring**: Built-in metrics tracking with memory usage, timing, and success rates
- **Mapping Management**: Centralized category mapping system with automatic detection of unmapped values

## 📁 Project Structure

```
Trivio_scrapper/
├── src/
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── base.py                 # Base scraper interface with enhanced logging
│   │   ├── funtrivia.py           # FunTrivia scraper with comprehensive error handling
│   │   ├── config.py              # Centralized mapping configuration
│   │   └── media.py               # Media download handler with proper naming
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── rate_limiter.py        # Advanced request rate limiting
│   │   ├── sheets.py              # Google Sheets integration with validation
│   │   ├── csv_handler.py         # CSV append/overwrite handling
│   │   ├── indexing.py            # Persistent question indexing
│   │   ├── validation.py          # Data validation and quality checks
│   │   ├── monitoring.py          # Performance monitoring and metrics
│   │   ├── compliance.py          # Ethical scraping compliance checks
│   │   ├── question_classifier.py # Question type classification
│   │   └── text_processor.py     # Text cleaning and processing
│   ├── constants.py               # Shared constants and configurations
│   └── main.py                    # Main script with enhanced CLI options
├── config/
│   ├── settings.json              # General configuration with enhanced options
│   └── mappings.json             # Category/difficulty mappings (centralized)
├── output/                        # CSV output files
├── assets/
│   ├── images/                    # Downloaded images with proper naming
│   └── audio/                     # Downloaded audio files with proper naming
├── logs/                          # Comprehensive application logs
├── credentials/                   # Google Sheets credentials (create manually)
├── examples/
│   ├── concurrency_demo.py       # Performance tuning examples
│   └── mapping_demo.py           # Mapping system demonstration
├── question_indices.json         # Persistent question indices
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker configuration
└── README.md                      # This comprehensive guide
```

## 🛠️ Installation & Setup

### Option 1: Local Development Setup

#### Prerequisites
- Python 3.11+
- pip
- Git

#### Step-by-Step Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Trivio_scrapper
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install chromium
   
   # For Linux users, install system dependencies
   sudo playwright install-deps chromium
   ```

5. **Create required directories**
   ```bash
   mkdir -p output assets/images assets/audio logs credentials
   ```

6. **Configure the application**
   ```bash
   # The scraper comes with default configurations
   # Optionally customize config/settings.json and config/mappings.json
   ```

7. **Test the installation**
   ```bash
   # Quick test with minimal questions
   python src/main.py --max-questions 5 --dry-run
   ```

8. **Run the scraper**
   ```bash
   # Start with safe settings
   python src/main.py --max-questions 100 --concurrency 2 --min-delay 2 --max-delay 4
   ```

### Option 2: Docker Setup

#### Prerequisites
- Docker
- Docker Compose (optional)

#### Docker Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Trivio_scrapper
   ```

2. **Build Docker image**
   ```bash
   docker build -t funtrivia-scraper .
   ```

3. **Run with Docker**
   ```bash
   # Basic run with safe settings
   docker run -v $(pwd)/output:/app/output \
              -v $(pwd)/assets:/app/assets \
              -v $(pwd)/logs:/app/logs \
              funtrivia-scraper --max-questions 100 --concurrency 2

   # With custom performance settings
   docker run -v $(pwd)/output:/app/output \
              -v $(pwd)/assets:/app/assets \
              funtrivia-scraper --max-questions 500 --concurrency 3 --min-delay 1 --max-delay 3

   # With Google Sheets (mount credentials)
   docker run -v $(pwd)/output:/app/output \
              -v $(pwd)/assets:/app/assets \
              -v $(pwd)/credentials:/app/credentials \
              funtrivia-scraper --upload-to-sheets \
              --sheets-credentials credentials/service-account.json \
              --sheets-id your_spreadsheet_id
   ```

4. **Using Docker Compose (Optional)**
   ```bash
   # Create docker-compose.yml with your preferred settings
   docker-compose up
   ```

## ⚙️ Enhanced Configuration

### Settings.json Configuration

Edit `config/settings.json` to customize the scraper behavior:

```json
{
  "scraper": {
    "base_url": "https://www.funtrivia.com",
    "max_questions_per_run": 1000,
    "concurrency": 3,
    "strict_mapping": false,
    "rate_limit": {
      "requests_per_minute": 30
    },
    "delays": {
      "min": 1.0,
      "max": 3.0
    },
    "timeouts": {
      "page_load": 60000,
      "network_idle": 45000,
      "quiz_page": 45000,
      "quiz_wait": 30000
    },
    "user_agents": [
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
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
    "enabled": false,
    "credentials_file": "credentials/service-account.json",
    "spreadsheet_id": ""
  },
  "logging": {
    "level": "INFO",
    "file": "logs/scraper.log",
    "max_size": 10485760,
    "backup_count": 5
  }
}
```

#### Enhanced Performance and Safety Configuration

**Concurrency Guidelines:**
- `concurrency`: Number of simultaneous browser instances (1-20)
  - **1-2**: Very safe, slow scraping (~8-15 questions/min), minimal detection risk ✅
  - **3-5**: Recommended balance of speed and safety (~20-40 questions/min) ✅
  - **6-10**: Fast but higher detection risk (~50-80 questions/min), monitor for blocks ⚠️
  - **10+**: High risk of IP blocking (~100+ questions/min), use with caution ❌

**Delay Configuration:**
- `delays.min`: Minimum delay between requests in seconds
- `delays.max`: Maximum delay between requests in seconds
  - **0.2-0.8s**: Aggressive, maximum speed, high detection risk ❌
  - **0.5-1.5s**: Fast scraping, moderate detection risk ⚠️
  - **1-3s**: Recommended for most use cases (default) ✅
  - **3-8s**: Conservative, slower but very safe ✅
  - **5-10s**: Ultra-conservative, minimal detection risk ✅

**Rate Limiting:**
- `rate_limit.requests_per_minute`: Maximum requests per minute across all browsers
  - Works in combination with delays and concurrency
  - Lower values = safer scraping, higher success rates

#### Performance Tuning Examples

**Ultra-Safe Scraping** (⭐ Recommended for new users):
```json
{
  "scraper": {
    "concurrency": 1,
    "delays": { "min": 5.0, "max": 10.0 },
    "rate_limit": { "requests_per_minute": 8 }
  }
}
```
*Expected: ~8 requests/min, 99% success rate, virtually no detection risk*

**Safe Scraping** (✅ Good for regular use):
```json
{
  "scraper": {
    "concurrency": 2,
    "delays": { "min": 3.0, "max": 8.0 },
    "rate_limit": { "requests_per_minute": 15 }
  }
}
```
*Expected: ~15 requests/min, 95% success rate, low detection risk*

**Balanced Scraping** (⚖️ Default recommendation):
```json
{
  "scraper": {
    "concurrency": 3,
    "delays": { "min": 1.0, "max": 3.0 },
    "rate_limit": { "requests_per_minute": 30 }
  }
}
```
*Expected: ~30 requests/min, 90% success rate, medium detection risk*

**Fast Scraping** (⚠️ Higher detection risk):
```json
{
  "scraper": {
    "concurrency": 6,
    "delays": { "min": 0.5, "max": 1.5 },
    "rate_limit": { "requests_per_minute": 60 }
  }
}
```
*Expected: ~60 requests/min, 80% success rate, high detection risk*

**Maximum Speed** (❌ Very high risk, not recommended):
```json
{
  "scraper": {
    "concurrency": 10,
    "delays": { "min": 0.2, "max": 0.8 },
    "rate_limit": { "requests_per_minute": 120 }
  }
}
```
*Expected: ~120 requests/min, 60% success rate, very high detection risk*

### Enhanced Logging Configuration

The scraper features comprehensive logging with the following capabilities:

#### Logging Levels and Output
- **File Logging**: Detailed logs with function names, line numbers, and timestamps
- **Console Logging**: Clean progress updates and status information
- **Rotating Logs**: Automatic log rotation when files exceed size limits
- **Error Tracking**: Full stack traces for debugging and troubleshooting

#### Logging Configuration Options
```json
{
  "logging": {
    "level": "INFO",           // DEBUG, INFO, WARNING, ERROR
    "file": "logs/scraper.log", // Log file path
    "max_size": 10485760,      // 10MB - rotate when exceeded
    "backup_count": 5          // Keep 5 backup files
  }
}
```

#### What Gets Logged
- **Session Information**: Start/end times, configuration, performance metrics
- **Category Processing**: Success/failure rates, quiz counts per category
- **Quiz Processing**: Individual quiz results with unique IDs for tracking
- **Question Processing**: Validation, formatting, and media download results
- **Error Handling**: Full stack traces while continuing processing
- **Mapping Issues**: Detailed tracking of unmapped categories for easy fixing
- **Media Downloads**: Success/failure with URLs and file paths
- **CSV Operations**: File operations, validation results, and sample data
- **Google Sheets**: Upload process with detailed error information

### Google Sheets Setup (Optional)

**⚠️ IMPORTANT: Google Sheets upload is DISABLED by default for privacy and security.**

The scraper can optionally upload results to Google Sheets for easy sharing and analysis. This feature requires explicit setup and activation.

#### Quick Setup Guide

1. **Test connection first:**
   ```bash
   python src/main.py --sheets-test-only \
     --sheets-credentials credentials/service-account.json \
     --sheets-id 1abc123def456ghi789jkl
   ```

2. **Enable upload via command line (recommended):**
   ```bash
   python src/main.py --upload-to-sheets \
     --sheets-credentials credentials/service-account.json \
     --sheets-id 1abc123def456ghi789jkl \
     --max-questions 100
   ```

#### Complete Google Sheets Setup

1. **Create Google Cloud Project**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Note the project ID for later reference

2. **Enable Google Sheets API**
   - Navigate to APIs & Services > Library
   - Search for "Google Sheets API" and enable it
   - Also enable "Google Drive API" for file access

3. **Create Service Account**
   - Go to APIs & Services > Credentials
   - Click "Create Credentials" > "Service Account"
   - Fill in service account details:
     - Name: `FunTrivia Scraper`
     - Description: `Service account for automated quiz data upload`
   - Click "Create and Continue"
   - Skip role assignment (click "Continue")
   - Click "Done"

4. **Generate Service Account Key**
   - Click on the created service account
   - Go to "Keys" tab
   - Click "Add Key" > "Create new key"
   - Choose "JSON" format
   - Download the file and save as `credentials/service-account.json`

5. **Setup Credentials Directory**
   ```bash
   mkdir -p credentials
   # Copy your downloaded JSON file to credentials/service-account.json
   chmod 600 credentials/service-account.json
   ```

6. **Create and Share Google Spreadsheet**
   - Create a new Google Spreadsheet
   - Open the JSON credentials file and find the `client_email` field
   - Share the spreadsheet with this email address (give "Editor" permissions)
   - Copy the spreadsheet ID from the URL (the long string between `/d/` and `/edit`)

7. **Test the Setup**
   ```bash
   python src/main.py --sheets-test-only \
     --sheets-credentials credentials/service-account.json \
     --sheets-id YOUR_SPREADSHEET_ID
   ```

#### Google Sheets CLI Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `--upload-to-sheets` | Enable Google Sheets upload (disabled by default) | No |
| `--no-sheets-upload` | Explicitly disable upload (overrides config file) | No |
| `--sheets-credentials PATH` | Path to service account JSON file | If uploading |
| `--sheets-id ID` | Google Spreadsheet ID from URL | If uploading |
| `--sheets-test-only` | Test connection and exit (no scraping) | No |

#### Usage Examples

**Enable Google Sheets upload:**
```bash
python src/main.py \
  --upload-to-sheets \
  --sheets-credentials credentials/service-account.json \
  --sheets-id 1abc123def456ghi789jkl \
  --max-questions 100 \
  --concurrency 2
```

**Test connection without scraping:**
```bash
python src/main.py --sheets-test-only \
  --sheets-credentials credentials/service-account.json \
  --sheets-id 1abc123def456ghi789jkl
```

**Disable sheets upload even if enabled in config:**
```bash
python src/main.py --no-sheets-upload --max-questions 50
```

## 🎯 Enhanced Usage Examples

### Basic Usage with New Options

```bash
# Scrape with safe default settings
python src/main.py --max-questions 100

# Enhanced concurrency control with validation
python src/main.py --max-questions 500 --concurrency 3 --min-delay 1 --max-delay 3

# Ultra-safe scraping for avoiding detection
python src/main.py --max-questions 200 --concurrency 1 --min-delay 5 --max-delay 10

# Fast scraping with higher risk (not recommended for beginners)
python src/main.py --max-questions 1000 --concurrency 6 --min-delay 0.5 --max-delay 1.5

# Validation and safety features
python src/main.py --max-questions 300 --concurrency 8  # Will show warning about high concurrency
python src/main.py --min-delay 3 --max-delay 1           # Will show error about invalid delay range
```

### Advanced Configuration Examples

```bash
# Custom configuration file
python src/main.py --config my-custom-config.json --max-questions 200

# Overwrite mode with automatic backup
python src/main.py --max-questions 200 --overwrite --backup

# Reset question indices and start fresh
python src/main.py --reset-indices --max-questions 100

# Dry run to test settings without saving data
python src/main.py --max-questions 50 --dry-run --concurrency 5

# Skip data validation for faster processing
python src/main.py --max-questions 1000 --skip-validation

# Validate existing CSV files only
python src/main.py --validate-only

# Enable strict mapping mode for data quality
python src/main.py --strict-mapping --max-questions 100
```

### Performance Tuning Examples

```bash
# Ultra-safe settings (recommended for new users)
python src/main.py --max-questions 100 --concurrency 1 --min-delay 5 --max-delay 10

# Safe balanced settings (recommended for regular use)
python src/main.py --max-questions 300 --concurrency 2 --min-delay 3 --max-delay 8

# Default balanced settings (good speed vs safety)
python src/main.py --max-questions 500 --concurrency 3 --min-delay 1 --max-delay 3

# Fast settings (higher detection risk, monitor closely)
python src/main.py --max-questions 800 --concurrency 6 --min-delay 0.5 --max-delay 1.5

# Maximum speed (very high risk, not recommended)
python src/main.py --max-questions 1000 --concurrency 10 --min-delay 0.2 --max-delay 0.8
```

### Category Collection and Management

```bash
# Collect all categories from the site for mapping analysis
python src/main.py --dump-categories-only --category-output-format both

# Collect categories to specific directory
python src/main.py --dump-categories-only --category-output-dir analysis --category-output-format csv

# Use strict mapping mode after updating mappings
python src/main.py --strict-mapping --max-questions 50 --dry-run
```

### Google Sheets Integration

```bash
# Test Google Sheets connection
python src/main.py --sheets-test-only \
  --sheets-credentials credentials/service-account.json \
  --sheets-id YOUR_SPREADSHEET_ID

# Scrape with Google Sheets upload
python src/main.py --upload-to-sheets \
  --sheets-credentials credentials/service-account.json \
  --sheets-id YOUR_SPREADSHEET_ID \
  --max-questions 200 --concurrency 2

# Disable Google Sheets even if enabled in config
python src/main.py --no-sheets-upload --max-questions 100
```

### Docker Usage Examples

```bash
# Basic Docker run with volume mounts
docker run -v $(pwd)/output:/app/output \
           -v $(pwd)/assets:/app/assets \
           -v $(pwd)/logs:/app/logs \
           funtrivia-scraper --max-questions 100 --concurrency 2

# Docker with Google Sheets support
docker run -v $(pwd)/output:/app/output \
           -v $(pwd)/assets:/app/assets \
           -v $(pwd)/credentials:/app/credentials \
           funtrivia-scraper \
           --upload-to-sheets \
           --sheets-credentials credentials/service-account.json \
           --sheets-id YOUR_ID \
           --max-questions 200

# Docker with custom performance settings
docker run -v $(pwd)/output:/app/output \
           -v $(pwd)/assets:/app/assets \
           funtrivia-scraper \
           --max-questions 500 \
           --concurrency 3 \
           --min-delay 1 \
           --max-delay 3
```

### Enhanced Command Line Arguments

| Parameter | Description | Default | Range/Options |
|-----------|-------------|---------|---------------|
| `--max-questions` | Maximum questions to scrape | 1000 | 1-unlimited |
| `--concurrency` | Number of concurrent browsers | 3 | 1-20 (warns >20) |
| `--min-delay` | Minimum delay between requests (seconds) | 1.0 | 0.1-60.0 |
| `--max-delay` | Maximum delay between requests (seconds) | 3.0 | 0.1-60.0 |
| `--config` | Path to configuration file | config/settings.json | Any valid path |
| `--categories` | Comma-separated category list | All categories | Category names |
| `--append` | Append to existing CSV files | True | flag |
| `--overwrite` | Overwrite existing CSV files | False | flag |
| `--backup` | Create backup before overwriting | False | flag |
| `--reset-indices` | Reset question indices to 0 | False | flag |
| `--validate-only` | Only validate existing CSV files | False | flag |
| `--skip-validation` | Skip data validation | False | flag |
| `--dry-run` | Simulate scraping without saving | False | flag |
| `--strict-mapping` | Enable strict mapping mode | False | flag |
| `--dump-categories-only` | Collect categories and exit | False | flag |
| `--category-output-dir` | Directory for category files | output | Any valid path |
| `--category-output-format` | Format for category files | both | json, csv, both |
| `--upload-to-sheets` | Enable Google Sheets upload | False | flag |
| `--no-sheets-upload` | Disable Google Sheets upload | False | flag |
| `--sheets-credentials` | Path to Google credentials | None | Path to JSON file |
| `--sheets-id` | Google Spreadsheet ID | None | Spreadsheet ID |
| `--sheets-test-only` | Test Google Sheets and exit | False | flag |

## 📊 Enhanced Output Format

### CSV Files and Structure

The scraper generates three main CSV files with enhanced validation and error handling:

1. **multiple_choice.csv** - Multiple choice questions (4 options)
2. **true_false.csv** - True/false questions (2 options)
3. **sound.csv** - Audio-based questions (4 options + audio file)

### Detailed CSV Structure

#### Multiple Choice Questions
```csv
Key,Domain,Topic,Difficulty,Question,Option1,Option2,Option3,Option4,CorrectAnswer,Hint,Description,ImagePath
Question_MC_Parsed_Culture_Normal_0001,Culture,Movies,Normal,"Who directed the movie 'Jaws'?",Steven Spielberg,George Lucas,Martin Scorsese,Francis Ford Coppola,Steven Spielberg,"Directed in 1975, this thriller became a summer blockbuster","Steven Spielberg's breakthrough film that established him as a major director in Hollywood",Question_MC_Parsed_Culture_Normal_0001.jpg
Question_MC_Parsed_Science_Hard_0002,Science,Physics,Hard,"What is the speed of light in a vacuum?",299792458 m/s,300000000 m/s,299000000 m/s,298000000 m/s,299792458 m/s,"Exact value defined by international standards","This is a fundamental constant of nature used to define the meter",
```

#### True/False Questions
```csv
Key,Domain,Topic,Difficulty,Question,Option1,Option2,CorrectAnswer,Hint,Description
Question_TF_Parsed_Science_Normal_0001,Science,Biology,Normal,"The human body has 206 bones",True,False,True,"Adult humans have this many bones after fusion","Babies are born with about 270 bones, but many fuse together as they grow"
Question_TF_Parsed_Geography_Easy_0002,Geography,Countries,Easy,"Australia is a continent",True,False,True,"Australia is both a country and continent","Australia is the smallest continent and the sixth-largest country by total area"
```

#### Sound Questions
```csv
Key,Domain,Topic,Difficulty,Question,Option1,Option2,Option3,Option4,CorrectAnswer,Hint,Description,AudioPath
Question_Sound_Parsed_Culture_Normal_0001,Culture,Music,Normal,"Which composer wrote this symphony?",Mozart,Beethoven,Bach,Chopin,Beethoven,"This is Symphony No. 9","Beethoven's final symphony, famous for 'Ode to Joy' in the fourth movement",Question_Sound_Parsed_Culture_Normal_0001.mp3
Question_Sound_Parsed_Nature_Easy_0002,Nature,Animals,Easy,"What animal makes this sound?",Dog,Cat,Cow,Horse,Dog,"Common domestic animal","Dogs bark for various reasons including alerting, playing, and communicating",Question_Sound_Parsed_Nature_Easy_0002.mp3
```

### Column Descriptions

| Column | Description | Example | Notes |
|--------|-------------|---------|-------|
| `Key` | Unique question identifier | `Question_MC_Parsed_Culture_Normal_0001` | Format: Question_{TYPE}_Parsed_{DOMAIN}_{DIFFICULTY}_{NUMBER} |
| `Domain` | Main subject category | `Culture`, `Science`, `Geography` | Mapped from site categories using centralized config |
| `Topic` | Specific topic within domain | `Movies`, `Physics`, `Countries` | Subcategory for more specific classification |
| `Difficulty` | Question difficulty level | `Easy`, `Normal`, `Hard` | Mapped from site difficulty indicators |
| `Question` | The actual question text | "Who directed the movie 'Jaws'?" | Cleaned and processed for consistency |
| `Option1-4` | Answer options | `Steven Spielberg`, `George Lucas` | Multiple choice has 4, true/false has 2 |
| `CorrectAnswer` | The correct answer | `Steven Spielberg` | Extracted from quiz results page |
| `Hint` | Additional hint or explanation | "Directed in 1975..." | Short explanatory text |
| `Description` | Detailed description | "Steven Spielberg's breakthrough..." | Extended information about the topic |
| `ImagePath` | Path to associated image | `Question_MC_Parsed_Culture_Normal_0001.jpg` | Only for questions with images |
| `AudioPath` | Path to associated audio | `Question_Sound_Parsed_Culture_Normal_0001.mp3` | Only for sound questions |

### File Organization

```
output/
├── multiple_choice.csv    # Questions with 4 options
├── true_false.csv        # Questions with 2 options (True/False)
└── sound.csv            # Questions with audio files

assets/
├── images/              # Downloaded images with localization key naming
│   ├── Question_MC_Parsed_Culture_Normal_0001.jpg
│   └── Question_MC_Parsed_Science_Hard_0002.png
└── audio/              # Downloaded audio files with localization key naming
    ├── Question_Sound_Parsed_Culture_Normal_0001.mp3
    └── Question_Sound_Parsed_Nature_Easy_0002.wav

logs/
├── scraper.log         # Main log file with detailed information
├── scraper.log.1       # Rotated log files (when main log exceeds 10MB)
└── scraper.log.2

question_indices.json   # Persistent question numbering across runs
```

### Data Quality Features

- **Validation**: All questions validated for completeness and format
- **Deduplication**: Automatic detection and handling of duplicate questions
- **Error Handling**: Individual question failures don't stop the entire process
- **Backup Support**: Optional automatic backups before overwriting
- **Append Mode**: Add new questions without losing existing data
- **Index Persistence**: Question numbering continues across multiple runs
- **Media Validation**: Downloaded media files are verified for integrity

## 🐛 Comprehensive Troubleshooting Guide

### Enhanced Debugging with Comprehensive Logging

The enhanced scraper provides detailed logging to help diagnose and resolve issues quickly:

#### Log File Locations
- **Main Log**: `logs/scraper.log` - Detailed information with function names and line numbers
- **Rotated Logs**: `logs/scraper.log.1`, `logs/scraper.log.2`, etc. - Automatic backups when logs exceed 10MB
- **Console Output**: Real-time progress and status updates

#### Log Analysis Commands
```bash
# View recent log entries
tail -f logs/scraper.log

# Search for specific errors
grep -i "error\|failed\|exception" logs/scraper.log

# View only warnings and errors
grep -E "(WARNING|ERROR)" logs/scraper.log

# Monitor quiz processing in real-time
tail -f logs/scraper.log | grep -E "(quiz|Quiz)"

# Check mapping issues
grep -i "unmapped\|mapping" logs/scraper.log

# View performance metrics
grep -i "performance\|memory\|duration" logs/scraper.log
```

#### Understanding Log Formats

**File Log Format**:
```
2024-01-15 10:30:45,123 - FunTriviaScraper - INFO - [_scrape_quiz:234] - [quiz123] Successfully completed quiz with 10 questions
```

**Console Log Format**:
```
10:30:45 - INFO - Starting quiz play-through process
```

### Common Issues and Enhanced Solutions

#### 1. Enhanced Playwright Installation and Browser Issues

**Problem**: Browser installation or launch failures
```
playwright: command not found
Error downloading browsers
Chromium executable not found
Browser launch timeout
```

**Enhanced Solutions**:
```bash
# Complete reinstallation with system dependencies
pip uninstall playwright playwright-stealth
pip install playwright==1.42.0
playwright install chromium
playwright install-deps chromium  # Linux only

# Verify installation with enhanced logging
python -c "
import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_browser():
    logger.info('Testing browser initialization...')
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=False)
        logger.info('Browser launched successfully')
        page = await browser.new_page()
        await page.goto('https://example.com')
        logger.info('Page navigation successful')
        await browser.close()
        logger.info('Browser test completed successfully')
    except Exception as e:
        logger.error(f'Browser test failed: {e}', exc_info=True)

asyncio.run(test_browser())
"

# Check browser path and permissions
python -c "
from playwright.async_api import async_playwright
import asyncio

async def check_browser():
    p = await async_playwright().start()
    print(f'Browser path: {p.chromium.executable_path}')
    
asyncio.run(check_browser())
"

# Debug browser launch with enhanced logging
python src/main.py --max-questions 1 --dry-run 2>&1 | tee browser_debug.log
```

#### 2. Enhanced Configuration and Validation Issues

**Problem**: Configuration errors or validation failures
```
Invalid delay configuration: min > max
High concurrency warning (>20)
Configuration file not found
JSON parsing errors
```

**Enhanced Solutions**:
```bash
# Validate configuration with enhanced error reporting
python -c "
import json
import sys

config_file = 'config/settings.json'
try:
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Validate delay configuration
    delays = config['scraper'].get('delays', {})
    min_delay = delays.get('min', 1.0)
    max_delay = delays.get('max', 3.0)
    
    if min_delay > max_delay:
        print(f'❌ Invalid delay config: min({min_delay}) > max({max_delay})')
        sys.exit(1)
    
    # Validate concurrency
    concurrency = config['scraper'].get('concurrency', 3)
    if concurrency > 20:
        print(f'⚠️ High concurrency warning: {concurrency} > 20')
    
    print('✅ Configuration validation passed')
    print(f'Concurrency: {concurrency}')
    print(f'Delays: {min_delay}-{max_delay}s')
    
except json.JSONDecodeError as e:
    print(f'❌ JSON parsing error: {e}')
    sys.exit(1)
except FileNotFoundError:
    print(f'❌ Configuration file not found: {config_file}')
    sys.exit(1)
except Exception as e:
    print(f'❌ Configuration error: {e}')
    sys.exit(1)
"

# Test configuration with dry run
python src/main.py --max-questions 5 --dry-run --concurrency 3 --min-delay 1 --max-delay 3

# Use debug logging for detailed validation
python src/main.py --max-questions 1 --dry-run 2>&1 | grep -E "(ERROR|WARNING|Configuration)"
```

#### 3. Enhanced Google Sheets Troubleshooting

**Problem**: Google Sheets authentication and upload failures
```
Authentication failed (403)
Spreadsheet not found (404)  
Service account permission denied
Credentials file format errors
```

**Enhanced Solutions with Detailed Logging**:

1. **Comprehensive Authentication Test**:
```bash
# Test with enhanced error reporting
python src/main.py --sheets-test-only \
  --sheets-credentials credentials/service-account.json \
  --sheets-id YOUR_SPREADSHEET_ID 2>&1 | tee sheets_debug.log

# Validate credentials file structure
python -c "
import json
import sys

try:
    with open('credentials/service-account.json', 'r') as f:
        creds = json.load(f)
    
    required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 
                      'client_email', 'client_id', 'auth_uri', 'token_uri']
    
    missing_fields = [field for field in required_fields if field not in creds]
    
    if missing_fields:
        print(f'❌ Missing required fields: {missing_fields}')
        sys.exit(1)
    
    print('✅ Credentials file structure valid')
    print(f'Service account email: {creds["client_email"]}')
    print(f'Project ID: {creds["project_id"]}')
    
except Exception as e:
    print(f'❌ Credentials validation failed: {e}')
    sys.exit(1)
"
```

2. **Test Spreadsheet Access**:
```bash
# Test spreadsheet access with detailed logging
python -c "
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import sys

try:
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        'credentials/service-account.json', scope)
    
    client = gspread.authorize(creds)
    
    # Test opening spreadsheet
    spreadsheet_id = 'YOUR_SPREADSHEET_ID'
    sheet = client.open_by_key(spreadsheet_id)
    
    print('✅ Google Sheets access successful')
    print(f'Spreadsheet title: {sheet.title}')
    print(f'Worksheet count: {len(sheet.worksheets())}')
    
except gspread.exceptions.APIError as e:
    print(f'❌ Google Sheets API error: {e}')
    print('Check: 1) API enabled 2) Spreadsheet shared 3) Correct permissions')
    sys.exit(1)
except Exception as e:
    print(f'❌ Authentication error: {e}')
    sys.exit(1)
"
```

#### 4. Enhanced Rate Limiting and Detection Avoidance

**Problem**: Getting blocked or rate limited with detailed error analysis
```
HTTP 429: Too Many Requests
HTTP 403: Forbidden  
Connection timeouts
Repeated quiz access failures
```

**Enhanced Solutions with Performance Monitoring**:

1. **Analyze Scraping Performance from Logs**:
```bash
# Check success rates from logs
grep -o "Quiz successful\|Quiz failed" logs/scraper.log | sort | uniq -c

# Monitor delay patterns
grep "Adding random delay" logs/scraper.log | tail -20

# Check rate limiting triggers
grep -i "rate limit\|429\|403" logs/scraper.log

# Analyze performance metrics
grep "Performance metrics" logs/scraper.log | tail -5
```

2. **Implement Ultra-Safe Settings**:
```bash
# Ultra-conservative settings for recovery
python src/main.py \
  --max-questions 50 \
  --concurrency 1 \
  --min-delay 8 \
  --max-delay 15

# Monitor with real-time logging
python src/main.py \
  --max-questions 10 \
  --concurrency 1 \
  --min-delay 5 \
  --max-delay 10 2>&1 | tee recovery.log
```

3. **Progressive Speed Increase**:
```bash
# Start ultra-safe and gradually increase speed
echo "Testing ultra-safe settings..."
python src/main.py --max-questions 10 --concurrency 1 --min-delay 10 --max-delay 15

echo "Testing safe settings..."
python src/main.py --max-questions 20 --concurrency 1 --min-delay 5 --max-delay 10

echo "Testing normal settings..."
python src/main.py --max-questions 50 --concurrency 2 --min-delay 3 --max-delay 8
```

#### 5. Enhanced Memory and Performance Issues

**Problem**: Memory issues and performance bottlenecks with detailed monitoring
```
MemoryError: Unable to allocate memory
Process killed (OOM)
Slow performance despite high concurrency
```

**Enhanced Solutions with Performance Tracking**:

1. **Monitor Resource Usage with Logging**:
```bash
# Monitor memory usage during scraping
python src/main.py --max-questions 100 --concurrency 3 &
SCRAPER_PID=$!

# Monitor in separate terminal
while kill -0 $SCRAPER_PID 2>/dev/null; do
    ps -p $SCRAPER_PID -o pid,ppid,pcpu,pmem,rss,vsz,comm
    sleep 30
done

# Check performance metrics from logs
grep -A 5 "Performance metrics:" logs/scraper.log
```

2. **Optimize Memory Usage**:
```bash
# Process in smaller batches with cleanup
for batch in {1..5}; do
    echo "Processing batch $batch..."
    python src/main.py --max-questions 100 --concurrency 2
    
    # Clear browser cache and temporary files
    rm -rf /tmp/playwright-*
    
    echo "Batch $batch completed, waiting 60 seconds..."
    sleep 60
done
```

#### 6. Enhanced Data Quality and Validation Issues

**Problem**: Data quality issues with comprehensive validation feedback
```
Missing correct answers
Malformed CSV output
Question validation failures
Mapping configuration issues
```

**Enhanced Solutions with Detailed Validation**:

1. **Comprehensive Data Validation**:
```bash
# Run full validation with detailed reporting
python src/main.py --validate-only 2>&1 | tee validation_report.log

# Check for specific data quality issues
python -c "
import pandas as pd
import sys

try:
    # Validate multiple choice questions
    df = pd.read_csv('output/multiple_choice.csv')
    
    print(f'Multiple Choice CSV: {len(df)} questions')
    
    # Check for missing data
    missing_questions = df['Question'].isna().sum()
    missing_answers = df['CorrectAnswer'].isna().sum()
    empty_options = (df[['Option1', 'Option2', 'Option3', 'Option4']].isna().all(axis=1)).sum()
    
    print(f'Missing questions: {missing_questions}')
    print(f'Missing correct answers: {missing_answers}')
    print(f'Empty option sets: {empty_options}')
    
    # Check answer validation
    valid_answers = 0
    for idx, row in df.iterrows():
        options = [row['Option1'], row['Option2'], row['Option3'], row['Option4']]
        if row['CorrectAnswer'] in options:
            valid_answers += 1
    
    print(f'Valid answer mapping: {valid_answers}/{len(df)} ({valid_answers/len(df)*100:.1f}%)')
    
    if missing_questions > 0 or missing_answers > 0 or empty_options > 0:
        print('❌ Data quality issues found')
        sys.exit(1)
    else:
        print('✅ Data quality validation passed')
        
except Exception as e:
    print(f'❌ Validation error: {e}')
    sys.exit(1)
"
```

2. **Check Mapping Configuration**:
```bash
# Validate mapping configuration
python -c "
from src.scraper.config import ScraperConfig

try:
    config = ScraperConfig('config/mappings.json')
    
    # Get mapping statistics
    stats = config.get_mapping_stats()
    
    print('Mapping Configuration Status:')
    for mapping_type, data in stats.items():
        print(f'  {mapping_type}: {data["total_mapped_values"]} mapped values')
    
    # Test some common mappings
    test_cases = [
        ('difficulty', ['easy', 'normal', 'hard']),
        ('domain', ['science', 'history', 'culture']),
        ('topic', ['general', 'movies', 'sports'])
    ]
    
    for mapping_type, test_values in test_cases:
        print(f'\nTesting {mapping_type} mappings:')
        for value in test_values:
            if mapping_type == 'difficulty':
                result = config.map_difficulty(value)
            elif mapping_type == 'domain':
                result = config.map_domain(value)
            else:
                result = config.map_topic(value)
            
            print(f'  "{value}" -> "{result}"')
    
    print('\n✅ Mapping configuration working correctly')
    
except Exception as e:
    print(f'❌ Mapping configuration error: {e}')
"

# Test with strict mapping mode
python src/main.py --strict-mapping --max-questions 5 --dry-run
```

### Advanced Debugging Techniques

#### 1. Comprehensive Session Analysis

```bash
# Generate comprehensive debugging report
python -c "
import json
import os
from datetime import datetime

print('=== FunTrivia Scraper Debug Report ===')
print(f'Generated: {datetime.now()}')
print()

# System info
print('System Information:')
print(f'Python version: {sys.version}')
print(f'Working directory: {os.getcwd()}')
print(f'Available disk space: {os.statvfs(".").f_bavail * os.statvfs(".").f_frsize / 1024**3:.1f} GB')
print()

# Check file structure
print('Project Structure:')
required_dirs = ['output', 'assets/images', 'assets/audio', 'logs', 'config']
for dir_path in required_dirs:
    exists = os.path.exists(dir_path)
    print(f'  {dir_path}: {"✅" if exists else "❌"}')

print()

# Configuration status
print('Configuration Status:')
try:
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    print('  settings.json: ✅')
    print(f'  Concurrency: {config["scraper"]["concurrency"]}')
    print(f'  Delays: {config["scraper"]["delays"]["min"]}-{config["scraper"]["delays"]["max"]}s')
except Exception as e:
    print(f'  settings.json: ❌ ({e})')

# CSV file status
print()
print('CSV File Status:')
csv_files = ['multiple_choice.csv', 'true_false.csv', 'sound.csv']
for csv_file in csv_files:
    path = f'output/{csv_file}'
    if os.path.exists(path):
        size = os.path.getsize(path)
        with open(path, 'r') as f:
            lines = sum(1 for _ in f) - 1  # Subtract header
        print(f'  {csv_file}: ✅ ({lines} questions, {size/1024:.1f} KB)')
    else:
        print(f'  {csv_file}: ❌ (not found)')

print()
print('Recent Log Entries:')
try:
    with open('logs/scraper.log', 'r') as f:
        lines = f.readlines()
    
    # Show last 10 lines
    for line in lines[-10:]:
        print(f'  {line.strip()}')
except Exception as e:
    print(f'  Log file error: {e}')
"
```

#### 2. Performance Profiling

```bash
# Profile scraper performance
python -m cProfile -o scraper_profile.stats src/main.py --max-questions 20 --concurrency 2

# Analyze performance profile
python -c "
import pstats
import sys

try:
    p = pstats.Stats('scraper_profile.stats')
    
    print('=== Top 20 Functions by Cumulative Time ===')
    p.sort_stats('cumulative').print_stats(20)
    
    print('\n=== Top 20 Functions by Total Time ===')
    p.sort_stats('tottime').print_stats(20)
    
    print('\n=== Scraper-Specific Functions ===')
    p.print_stats('scraper|funtrivia')
    
except Exception as e:
    print(f'Profile analysis failed: {e}')
"
```

#### 3. Network and Connectivity Testing

```bash
# Comprehensive network testing
python -c "
import requests
import time
import statistics

def test_connectivity():
    print('=== Network Connectivity Test ===')
    
    # Test basic connectivity
    try:
        response = requests.get('https://www.funtrivia.com/', timeout=10)
        print(f'FunTrivia access: ✅ (Status: {response.status_code})')
    except Exception as e:
        print(f'FunTrivia access: ❌ ({e})')
        return
    
    # Test response times
    times = []
    for i in range(5):
        try:
            start = time.time()
            response = requests.get('https://www.funtrivia.com/', timeout=10)
            end = time.time()
            times.append(end - start)
            print(f'Request {i+1}: {end-start:.2f}s')
        except Exception as e:
            print(f'Request {i+1}: Failed ({e})')
    
    if times:
        avg_time = statistics.mean(times)
        print(f'Average response time: {avg_time:.2f}s')
        
        if avg_time > 5:
            print('⚠️ Slow response times detected - consider increasing delays')
        elif avg_time < 1:
            print('✅ Fast response times - current delays should be sufficient')

test_connectivity()
"
```

### Recovery Procedures

#### 1. Soft Recovery (Resume from Errors)

```bash
# Resume with safe settings after errors
python src/main.py \
  --max-questions 50 \
  --concurrency 1 \
  --min-delay 5 \
  --max-delay 10 \
  --append

# Check if recovery is working
tail -f logs/scraper.log | grep -E "(SUCCESS|completed|questions)"
```

#### 2. Hard Recovery (Reset and Restart)

```bash
# Complete reset and restart
echo "Performing hard recovery..."

# Backup existing data
mkdir -p backups/$(date +%Y%m%d_%H%M%S)
cp -r output/* backups/$(date +%Y%m%d_%H%M%S)/ 2>/dev/null || true
cp question_indices.json backups/$(date +%Y%m%d_%H%M%S)/ 2>/dev/null || true

# Reset indices and start fresh
python src/main.py --reset-indices

# Start with ultra-safe settings
python src/main.py \
  --max-questions 20 \
  --concurrency 1 \
  --min-delay 10 \
  --max-delay 20 \
  --overwrite \
  --backup

echo "Hard recovery completed"
```

#### 3. Configuration Recovery

```bash
# Restore default configuration
python -c "
import json

default_config = {
    'scraper': {
        'base_url': 'https://www.funtrivia.com',
        'max_questions_per_run': 1000,
        'concurrency': 2,
        'strict_mapping': False,
        'rate_limit': {'requests_per_minute': 20},
        'delays': {'min': 3.0, 'max': 8.0},
        'timeouts': {
            'page_load': 60000,
            'network_idle': 45000,
            'quiz_page': 45000,
            'quiz_wait': 30000
        },
        'user_agents': [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
    },
    'storage': {
        'output_dir': 'output',
        'images_dir': 'assets/images',
        'audio_dir': 'assets/audio',
        'csv_files': {
            'multiple_choice': 'multiple_choice.csv',
            'true_false': 'true_false.csv',
            'sound': 'sound.csv'
        }
    },
    'google_sheets': {
        'enabled': False,
        'credentials_file': 'credentials/service-account.json',
        'spreadsheet_id': ''
    },
    'logging': {
        'level': 'INFO',
        'file': 'logs/scraper.log',
        'max_size': 10485760,
        'backup_count': 5
    }
}

with open('config/settings.json', 'w') as f:
    json.dump(default_config, f, indent=2)

print('✅ Default configuration restored')
print('🔧 Edit config/settings.json to customize settings')
"
```

### Getting Help and Support

#### 1. Automated Diagnostics

```bash
# Run comprehensive diagnostics
python -c "
import subprocess
import sys
import os

print('=== Automated Diagnostics ===')

# Check Python environment
print(f'Python version: {sys.version}')

# Check installed packages
try:
    result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True)
    important_packages = ['playwright', 'pandas', 'gspread', 'tenacity']
    
    for package in important_packages:
        if package in result.stdout:
            print(f'{package}: ✅ Installed')
        else:
            print(f'{package}: ❌ Missing')
except Exception as e:
    print(f'Package check failed: {e}')

# Test basic imports
imports_to_test = [
    'playwright.async_api',
    'pandas',
    'gspread',
    'tenacity'
]

for import_name in imports_to_test:
    try:
        __import__(import_name)
        print(f'Import {import_name}: ✅')
    except ImportError as e:
        print(f'Import {import_name}: ❌ ({e})')

print('\n=== System Status ===')
print(f'Current directory: {os.getcwd()}')
print(f'Config file exists: {os.path.exists("config/settings.json")}')
print(f'Output directory exists: {os.path.exists("output")}')
print(f'Log directory exists: {os.path.exists("logs")}')
"

# Test scraper initialization
python src/main.py --max-questions 1 --dry-run
```

#### 2. Collect Debug Information

```bash
# Collect comprehensive debug information
echo "Collecting debug information..." > debug_info.txt
echo "Generated: $(date)" >> debug_info.txt
echo "" >> debug_info.txt

echo "=== System Information ===" >> debug_info.txt
uname -a >> debug_info.txt
python --version >> debug_info.txt
echo "" >> debug_info.txt

echo "=== Configuration ===" >> debug_info.txt
cat config/settings.json >> debug_info.txt 2>/dev/null || echo "Config file not found" >> debug_info.txt
echo "" >> debug_info.txt

echo "=== Recent Logs ===" >> debug_info.txt
tail -50 logs/scraper.log >> debug_info.txt 2>/dev/null || echo "Log file not found" >> debug_info.txt
echo "" >> debug_info.txt

echo "=== File Structure ===" >> debug_info.txt
find . -type f -name "*.csv" -o -name "*.json" -o -name "*.log" | head -20 >> debug_info.txt

echo "Debug information collected in debug_info.txt"
echo "Share this file when reporting issues"
```

## 📈 Performance Optimization and Best Practices

### Recommended Performance Profiles

Based on extensive testing, here are the recommended performance profiles for different use cases:

#### 1. **New User Profile** (⭐ Recommended for beginners)
```bash
python src/main.py \
  --max-questions 50 \
  --concurrency 1 \
  --min-delay 5 \
  --max-delay 10

# Expected: ~6-8 questions/min, 99% success rate, virtually no detection risk
```

#### 2. **Safe Production Profile** (✅ Recommended for regular use)
```bash
python src/main.py \
  --max-questions 200 \
  --concurrency 2 \
  --min-delay 3 \
  --max-delay 8

# Expected: ~15-20 questions/min, 95% success rate, low detection risk
```

#### 3. **Balanced Performance Profile** (⚖️ Default recommendation)
```bash
python src/main.py \
  --max-questions 500 \
  --concurrency 3 \
  --min-delay 1 \
  --max-delay 3

# Expected: ~30-40 questions/min, 90% success rate, medium detection risk
```

#### 4. **High-Speed Profile** (⚠️ Use with monitoring)
```bash
python src/main.py \
  --max-questions 1000 \
  --concurrency 6 \
  --min-delay 0.5 \
  --max-delay 1.5

# Expected: ~60-80 questions/min, 80% success rate, high detection risk
# Monitor logs for rate limiting warnings
```

### Performance Monitoring Commands

```bash
# Monitor real-time performance
tail -f logs/scraper.log | grep -E "(Performance metrics|SUCCESS|FAILED)"

# Check success rates
grep -c "Successfully processed" logs/scraper.log
grep -c "Failed to scrape" logs/scraper.log

# Monitor memory usage
ps aux | grep "python src/main.py" | awk '{print $4, $5, $6}'

# Watch CSV file growth
watch -n 30 'wc -l output/*.csv'
```

### Optimization Guidelines

1. **Start Conservative**: Begin with safe settings and gradually increase speed
2. **Monitor Success Rates**: Keep success rates above 85% for sustainable scraping
3. **Use Appropriate Hardware**: More concurrent browsers require more RAM and CPU
4. **Network Considerations**: Faster internet allows for higher concurrency
5. **Respect Rate Limits**: Lower settings during peak hours for the website
6. **Regular Monitoring**: Check logs regularly for warnings and errors

## 🔧 Development and Customization

### Adding New Question Types

The scraper is designed to be extensible. To add support for new question types:

1. **Update Question Classifier** (`src/utils/question_classifier.py`):
```python
def classify(self, question_text: str, options: List[str]) -> str:
    # Add logic for new question type
    if self._is_new_type(question_text, options):
        return 'new_type'
    # ... existing logic
```

2. **Update CSV Handler** (`src/utils/csv_handler.py`):
```python
def get_csv_template(self, question_type: str) -> List[str]:
    templates = {
        'new_type': ['Key', 'Domain', 'Topic', 'Difficulty', 'Question', 
                    'CustomField1', 'CustomField2', 'CorrectAnswer']
    }
    return templates.get(question_type, self.default_template)
```

3. **Update Configuration** (`config/settings.json`):
```json
{
  "storage": {
    "csv_files": {
      "new_type": "new_type.csv"
    }
  }
}
```

### Custom Scrapers for Other Sites

To create scrapers for other trivia sites:

1. **Inherit from BaseScraper**:
```python
from scraper.base import BaseScraper

class NewSiteScraper(BaseScraper):
    async def scrape_questions(self, max_questions=None):
        # Implement site-specific logic
        pass
```

2. **Implement Required Methods**:
- `initialize()`: Set up browser and connections
- `close()`: Clean up resources
- `scrape_questions()`: Main scraping logic
- `download_media()`: Handle media files

3. **Add Site Configuration**:
```json
{
  "scraper": {
    "base_url": "https://newsite.com",
    "site_specific_config": {
      "custom_setting": "value"
    }
  }
}
```

### Testing and Quality Assurance

```bash
# Run with validation enabled
python src/main.py --max-questions 10 --validate-only

# Test specific components
python -c "
from src.utils.validation import validate_scraped_data
from src.scraper.config import ScraperConfig

# Test mapping system
config = ScraperConfig('config/mappings.json')
print('Mapping system working:', config.validate_mappings())
"

# Test Google Sheets integration
python src/main.py --sheets-test-only \
  --sheets-credentials credentials/service-account.json \
  --sheets-id YOUR_SPREADSHEET_ID
```

### Code Quality Tools

```bash
# Install development dependencies
pip install black isort flake8 mypy pytest pytest-asyncio

# Format code
black src/
isort src/

# Check code quality
flake8 src/ --max-line-length=100
mypy src/ --ignore-missing-imports

# Run tests (if available)
pytest tests/ -v
```

## 📝 License and Legal

This project is licensed under the MIT License - see the LICENSE file for details.

### Important Legal Considerations

- **Respect robots.txt**: Always check and respect the website's robots.txt file
- **Rate Limiting**: Use appropriate delays to avoid overwhelming the target server
- **Terms of Service**: Ensure compliance with the website's terms of service
- **Personal Use**: This tool is intended for educational and personal use
- **Data Usage**: Respect copyright and intellectual property rights of scraped content

### Ethical Usage Guidelines

1. **Responsible Scraping**: Use conservative settings to minimize server load
2. **Attribution**: Credit the original source when using scraped content
3. **Compliance**: Follow all applicable laws and regulations
4. **Monitoring**: Regularly check for changes in the website's terms
5. **Community**: Contribute improvements back to the open-source community

## 🤝 Contributing

We welcome contributions to improve the FunTrivia scraper! Here's how you can help:

### Contributing Guidelines

1. **Fork the Repository**
   ```bash
   git clone https://github.com/your-username/Trivio_scrapper.git
   cd Trivio_scrapper
   ```

2. **Create Feature Branch**
   ```bash
   git checkout -b feature/amazing-new-feature
   ```

3. **Make Changes**
   - Follow the existing code style
   - Add comprehensive logging for new features
   - Update documentation and README
   - Add tests if applicable

4. **Test Changes**
   ```bash
   # Test basic functionality
   python src/main.py --max-questions 5 --dry-run
   
   # Test with different configurations
   python src/main.py --max-questions 10 --concurrency 2 --min-delay 2 --max-delay 5
   
   # Validate code quality
   black src/ && flake8 src/
   ```

5. **Commit Changes**
   ```bash
   git add .
   git commit -m "Add amazing new feature: detailed description"
   ```

6. **Push and Create Pull Request**
   ```bash
   git push origin feature/amazing-new-feature
   ```

### Areas for Contribution

- **New Website Scrapers**: Add support for other trivia sites
- **Enhanced Question Types**: Support for more complex question formats
- **UI Improvements**: Web interface or GUI for easier configuration
- **Performance Optimizations**: Speed and memory usage improvements
- **Testing**: Comprehensive test suite development
- **Documentation**: Examples, tutorials, and guides

### Development Setup

```bash
# Clone repository
git clone <repository-url>
cd Trivio_scrapper

# Set up development environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies with development tools
pip install -r requirements.txt
pip install black isort flake8 mypy pytest pytest-asyncio

# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

## 📞 Support and Community

### Getting Help

1. **Check the Documentation**: Most issues are covered in this comprehensive README
2. **Search Existing Issues**: Look for similar problems in the GitHub issues
3. **Use Diagnostic Tools**: Run the automated diagnostic commands provided
4. **Check Logs**: The enhanced logging system provides detailed error information

### Reporting Issues

When reporting issues, please include:

```bash
# Generate debug report
python -c "
import sys
import os
import json
from datetime import datetime

print('=== Issue Report ===')
print(f'Date: {datetime.now()}')
print(f'Python: {sys.version}')
print(f'OS: {os.name}')

try:
    with open('config/settings.json', 'r') as f:
        config = json.load(f)
    print(f'Concurrency: {config["scraper"]["concurrency"]}')
    print(f'Delays: {config["scraper"]["delays"]}')
except:
    print('Config: Not available')

print()
print('Recent log entries:')
try:
    with open('logs/scraper.log', 'r') as f:
        lines = f.readlines()[-20:]
    for line in lines:
        print(line.strip())
except:
    print('Logs: Not available')
"

# Include command that caused the issue
echo "Command used:"
echo "python src/main.py --max-questions 100 --concurrency 3"

# Include error message
echo "Error message:"
echo "Paste the full error message here"
```

### Community Resources

- **GitHub Issues**: For bug reports and feature requests
- **GitHub Discussions**: For questions and community support
- **Wiki**: Additional documentation and tutorials
- **Examples**: Sample configurations and use cases

## 🔄 Project Status and Roadmap

### Current Status (v2.0.0)

✅ **Completed Features**:
- Comprehensive logging system with file rotation
- Advanced concurrency controls with safety validation
- Enhanced Google Sheets integration with detailed error handling
- Centralized mapping configuration system
- Robust error handling with individual quiz/question failure recovery
- Performance monitoring and metrics tracking
- Enhanced CLI with extensive validation
- Complete troubleshooting and debugging tools
- Docker support with volume mounting
- Comprehensive documentation and examples

### Upcoming Features (v2.1.0)

🚧 **In Development**:
- Web interface for easier configuration and monitoring
- Advanced filtering and search capabilities for scraped data
- Export to additional formats (Excel, JSON, XML)
- Integration with more trivia websites
- Advanced analytics and reporting features
- Automated scheduling and periodic scraping
- Enhanced media processing and validation

### Long-term Roadmap (v3.0.0)

🔮 **Future Plans**:
- Machine learning-based question classification
- Natural language processing for better answer extraction
- Distributed scraping across multiple machines
- Real-time collaboration features
- Advanced data deduplication and quality assurance
- Plugin system for custom extensions
- REST API for integration with other applications

### Version History

- **v2.0.0** (Current): Enhanced logging, concurrency controls, comprehensive error handling
- **v1.2.0**: Google Sheets integration, Docker support, improved media handling
- **v1.1.0**: Multiple question types, persistent indexing, CSV append mode
- **v1.0.0**: Initial release with basic FunTrivia scraping capabilities

### Contributing to the Roadmap

We welcome suggestions for new features and improvements:

1. **Feature Requests**: Create detailed GitHub issues for new features
2. **Vote on Features**: Use GitHub reactions to vote on proposed features
3. **Contribute Code**: Submit pull requests for features you'd like to implement
4. **Testing**: Help test beta features and provide feedback
5. **Documentation**: Improve documentation and create tutorials

---

## 🎉 Conclusion

The FunTrivia Quiz Scraper provides a comprehensive, robust, and ethical solution for extracting quiz questions from FunTrivia.com. With its enhanced logging, configurable concurrency controls, comprehensive error handling, and extensive documentation, it's designed to be both powerful for advanced users and accessible for beginners.

### Key Strengths

- **Reliability**: Robust error handling ensures consistent operation
- **Safety**: Built-in protections against detection and rate limiting
- **Flexibility**: Extensive configuration options for all use cases
- **Transparency**: Comprehensive logging provides complete visibility
- **Quality**: Data validation and quality assurance throughout the process
- **Support**: Extensive documentation and troubleshooting guides

### Getting Started Checklist

- [ ] Install Python 3.11+ and create virtual environment
- [ ] Install dependencies with `pip install -r requirements.txt`
- [ ] Install Playwright browsers with `playwright install chromium`
- [ ] Create required directories with `mkdir -p output assets/images assets/audio logs`
- [ ] Run initial test with `python src/main.py --max-questions 5 --dry-run`
- [ ] Review configuration in `config/settings.json`
- [ ] Start scraping with safe settings: `python src/main.py --max-questions 100 --concurrency 2`
- [ ] Monitor logs in `logs/scraper.log` for any issues
- [ ] Gradually increase performance settings as needed

### Final Notes

Remember to always use this tool responsibly and ethically. Start with conservative settings, monitor the logs for any issues, and respect the target website's servers. The comprehensive logging and safety features are designed to help you scrape effectively while minimizing risks.

For questions, issues, or contributions, please use the GitHub repository's issue tracker and discussion forums. The community is here to help you get the most out of this powerful scraping tool.

**Happy scraping! 🚀** 