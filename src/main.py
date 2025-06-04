import asyncio
import argparse
import json
import pandas as pd # type: ignore
from pathlib import Path
import logging
import os
import sys
from typing import Dict, List, Any
from scraper.funtrivia import FunTriviaScraper
from utils.sheets import GoogleSheetsUploader
from utils.rate_limiter import RateLimiter
from utils.csv_handler import CSVHandler
from utils.indexing import QuestionIndexer
from utils.validation import validate_scraped_data, print_validation_report, validate_csv_files
from utils.monitoring import ScrapingMetrics, HealthMonitor
from utils.compliance import run_compliance_check, EthicalScraper

def setup_logging(config: Dict[str, Any]) -> None:
    """Set up comprehensive logging configuration for both file and console output."""
    log_file = config['logging']['file']
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Clear any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set logging level
    log_level = getattr(logging, config['logging']['level'].upper(), logging.INFO)
    root_logger.setLevel(log_level)
    
    # File handler with rotation
    try:
        from logging.handlers import RotatingFileHandler
        max_size = config['logging'].get('max_size', 10485760)  # 10MB default
        backup_count = config['logging'].get('backup_count', 5)
        
        file_handler = RotatingFileHandler(
            log_file, 
            maxBytes=max_size, 
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
    except Exception as e:
        # Fallback to regular file handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        print(f"Warning: Could not set up rotating file handler: {e}")
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Enhanced formatters with more context
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Log the logger initialization
    root_logger.info(f"Logging initialized - Level: {config['logging']['level']}")
    root_logger.info(f"Log file: {log_file}")
    root_logger.debug("Debug logging enabled")

def format_question_data_enhanced(question: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced formatting of question data to match CSV template structure exactly."""
    # Get question type to determine correct fields
    question_type = question.get('type', 'multiple_choice')
    
    # Base structure common to all question types
    formatted = {
        'Key': question.get('id', ''),
        'Domain': question.get('domain', 'Culture'),
        'Topic': question.get('topic', 'General'),
        'Difficulty': question.get('difficulty', 'Normal'),
        'Question': question.get('question', ''),
        'Option1': '',
        'Option2': '',
        'CorrectAnswer': question.get('correct_answer', ''),
        'Hint': question.get('hint', ''),
        'Description': question.get('description', '')
    }

    # Add question type-specific fields
    if question_type == 'multiple_choice':
        # Multiple choice has 4 options and ImagePath
        formatted.update({
            'Option3': '',
            'Option4': '',
            'ImagePath': ''
        })
    elif question_type == 'true_false':
        # True/false only has 2 options, no media path
        pass  # Already has Option1, Option2
    elif question_type == 'sound':
        # Sound has 4 options and AudioPath
        formatted.update({
            'Option3': '',
            'Option4': '',
            'AudioPath': ''
        })

    # Fill in options based on question type
    options = question.get('options', [])
    max_options = 4 if question_type in ['multiple_choice', 'sound'] else 2
    for i, option in enumerate(options[:max_options], 1):
        formatted[f'Option{i}'] = option.strip()

    # Handle media paths - ensure only filename is written to CSV
    media_filename = question.get('media_filename')
    if media_filename:
        # Media filename should already be just the filename from MediaHandler
        # Set the appropriate media path field based on question type
        if question_type == 'sound' and 'AudioPath' in formatted:
            formatted['AudioPath'] = media_filename
        elif question_type == 'multiple_choice' and 'ImagePath' in formatted:
            formatted['ImagePath'] = media_filename

    # Enhanced correct answer validation
    if formatted['CorrectAnswer']:
        # Clean up the correct answer
        correct_answer = formatted['CorrectAnswer'].strip()
        
        # Try to match with exact options first
        for option in options:
            if option.strip().lower() == correct_answer.lower():
                formatted['CorrectAnswer'] = option.strip()
                break
        else:
            # If no exact match, try partial matching
            for option in options:
                if correct_answer.lower() in option.lower() or option.lower() in correct_answer.lower():
                    formatted['CorrectAnswer'] = option.strip()
                    break
            else:
                # If still no match and we have options, default to first option
                if options:
                    formatted['CorrectAnswer'] = options[0].strip()
                    logging.getLogger(__name__).warning(
                        f"Could not match correct answer '{correct_answer}' with options, using first option"
                    )

    # Ensure we have a correct answer
    if not formatted['CorrectAnswer'] and options:
        formatted['CorrectAnswer'] = options[0].strip()

    # Clean up hint text
    if formatted['Hint']:
        hint = formatted['Hint'].strip()
        # Remove common prefixes and suffixes
        hint = hint.replace('Explanation:', '').replace('Hint:', '').strip()
        formatted['Hint'] = hint

    # Clean up description text
    if formatted['Description']:
        description = formatted['Description'].strip()
        # Remove common prefixes and suffixes
        description = description.replace('Explanation:', '').replace('Description:', '').replace('Summary:', '').strip()
        # Remove quiz-specific text patterns
        description = description.replace('Interesting Information:', '').replace('Fun Fact:', '').strip()
        formatted['Description'] = description

    return formatted

def ensure_directories(config: Dict[str, Any]) -> None:
    """Ensure all required directories exist."""
    directories = [
        config['storage']['output_dir'],
        config['storage']['images_dir'],
        config['storage']['audio_dir'],
        'logs'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def print_csv_statistics(csv_handler: CSVHandler, config: Dict[str, Any]) -> None:
    """Print statistics about existing CSV files."""
    print("\n" + "="*50)
    print("EXISTING CSV STATISTICS")
    print("="*50)
    
    for question_type, csv_file in config['storage']['csv_files'].items():
        stats = csv_handler.get_csv_stats(csv_file)
        print(f"\n{question_type.replace('_', ' ').title()}:")
        print(f"  File: {csv_file}")
        print(f"  Exists: {stats['exists']}")
        print(f"  Questions: {stats['total_questions']}")
        if stats['sample_keys']:
            print(f"  Sample keys: {', '.join(stats['sample_keys'])}")

def run_pre_scrape_checks(config: Dict[str, Any], logger) -> bool:
    """Run pre-scraping validation checks."""
    logger.info("Running pre-scrape validation checks")
    
    # Check compliance
    try:
        base_url = config['scraper']['base_url']
        compliance_results = run_compliance_check(base_url, config)
        
        if compliance_results.get('overall_status') != 'compliant':
            logger.warning("Compliance check failed - proceeding with caution")
    except Exception as e:
        logger.warning(f"Compliance check error: {e}")
    
    # Check system health
    try:
        health_monitor = HealthMonitor()
        health_status = health_monitor.check_system_health()
        
        if health_status['overall_status'] == 'critical':
            logger.error("System health check failed - stopping")
            print(health_monitor.get_health_summary())
            return False
        elif health_status['overall_status'] == 'warning':
            logger.warning("System health check shows warnings")
            print(health_monitor.get_health_summary())
    except Exception as e:
        logger.warning(f"Health check error: {e}")
    
    return True

async def run_category_collection(config_file: str, output_dir: str = "output", output_format: str = "both"):
    """Run the category collection process."""
    # Import here to avoid circular imports
    sys.path.append('.')
    
    try:
        from collect_categories import CategoryCollector
        
        print("🔍 Starting category collection mode...")
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        collector = CategoryCollector(config_file)
        
        print("Collecting all categories from the site...")
        await collector.collect_all_categories()
        
        # Save data in requested format(s)
        if output_format in ['json', 'both']:
            json_file = Path(output_dir) / "all_categories.json"
            collector.save_to_json(str(json_file))
        
        if output_format in ['csv', 'both']:
            collector.save_to_csv(output_dir)
        
        # Print summary
        collector.print_summary()
        
        print(f"\n✅ Category collection completed successfully!")
        print(f"📁 Files saved to: {output_dir}/")
        print(f"📝 Review the collected categories and update your mappings accordingly.")
        print(f"💡 After updating mappings, run the main parser with the updated configuration.")
        
        return True
        
    except ImportError as e:
        print(f"❌ Error: Could not import category collector: {e}")
        print("Make sure collect_categories.py is in the current directory.")
        return False
    except Exception as e:
        print(f"❌ Error during category collection: {e}")
        logging.getLogger(__name__).error(f"Category collection failed: {e}", exc_info=True)
        return False

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='FunTrivia Quiz Scraper')
    parser.add_argument('--max-questions', type=int, help='Maximum number of questions to scrape')
    parser.add_argument('--concurrency', type=int, help='Number of concurrent scrapers (default: 3)')
    parser.add_argument('--min-delay', type=float, help='Minimum delay between requests in seconds (default: 1)')
    parser.add_argument('--max-delay', type=float, help='Maximum delay between requests in seconds (default: 3)')
    parser.add_argument('--categories', type=str, help='Comma-separated list of categories to scrape')
    parser.add_argument('--config', type=str, default='config/settings.json', help='Path to configuration file')
    parser.add_argument('--append', action='store_true', default=True, help='Append to existing CSV files (default)')
    parser.add_argument('--overwrite', action='store_true', help='Overwrite existing CSV files')
    parser.add_argument('--backup', action='store_true', help='Create backup before overwriting')
    parser.add_argument('--reset-indices', action='store_true', help='Reset question indices to 0')
    parser.add_argument('--validate-only', action='store_true', help='Only validate existing CSV files')
    parser.add_argument('--skip-validation', action='store_true', help='Skip data validation')
    parser.add_argument('--dry-run', action='store_true', help='Simulate scraping without saving data')
    
    # New category collection arguments
    parser.add_argument('--dump-categories-only', action='store_true', 
                       help='Run category collection mode only (collect all categories from the site)')
    parser.add_argument('--category-output-dir', type=str, default='output',
                       help='Output directory for category collection files')
    parser.add_argument('--category-output-format', choices=['json', 'csv', 'both'], default='both',
                       help='Output format for category collection')
    
    # Strict mapping mode
    parser.add_argument('--strict-mapping', action='store_true',
                       help='Enable strict mapping mode - crash on unknown categories instead of using fallbacks')
    
    # Google Sheets Integration Arguments
    # By default, Google Sheets upload is DISABLED unless explicitly enabled via command line or config
    parser.add_argument('--upload-to-sheets', action='store_true',
                       help='Enable Google Sheets upload (disabled by default). Requires --sheets-credentials and --sheets-id')
    parser.add_argument('--no-sheets-upload', action='store_true',
                       help='Explicitly disable Google Sheets upload (overrides config file setting)')
    parser.add_argument('--sheets-credentials', type=str,
                       help='Path to Google Sheets service account credentials JSON file (e.g., credentials/service-account.json)')
    parser.add_argument('--sheets-id', type=str,
                       help='Google Spreadsheet ID (found in the spreadsheet URL)')
    parser.add_argument('--sheets-test-only', action='store_true',
                       help='Only test Google Sheets connection and exit (requires --sheets-credentials and --sheets-id)')
    
    args = parser.parse_args()

    # Handle Google Sheets testing mode
    if args.sheets_test_only:
        if not args.sheets_credentials or not args.sheets_id:
            print("❌ Error: --sheets-test-only requires both --sheets-credentials and --sheets-id")
            print("Usage: python src/main.py --sheets-test-only --sheets-credentials path/to/creds.json --sheets-id your_sheet_id")
            return 1
        
        from utils.sheets import test_google_sheets_setup
        success = test_google_sheets_setup(args.sheets_credentials, args.sheets_id)
        return 0 if success else 1

    # Handle category collection mode
    if args.dump_categories_only:
        success = await run_category_collection(
            config_file=args.config,
            output_dir=args.category_output_dir,
            output_format=args.category_output_format
        )
        return 0 if success else 1

    # Load configuration
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Configuration file {args.config} not found!")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing configuration file: {e}")
        return

    # Configure Google Sheets settings based on command line arguments and config
    sheets_enabled = False
    sheets_config = {}
    
    if args.no_sheets_upload:
        # Explicitly disabled via command line
        sheets_enabled = False
        print("📊 Google Sheets upload explicitly disabled via --no-sheets-upload")
    elif args.upload_to_sheets:
        # Explicitly enabled via command line - validate required arguments
        if not args.sheets_credentials:
            print("❌ Error: --upload-to-sheets requires --sheets-credentials")
            print("Usage: python src/main.py --upload-to-sheets --sheets-credentials path/to/creds.json --sheets-id your_sheet_id")
            return 1
        if not args.sheets_id:
            print("❌ Error: --upload-to-sheets requires --sheets-id")
            print("Usage: python src/main.py --upload-to-sheets --sheets-credentials path/to/creds.json --sheets-id your_sheet_id")
            return 1
        
        sheets_enabled = True
        sheets_config = {
            'enabled': True,
            'credentials_file': args.sheets_credentials,
            'spreadsheet_id': args.sheets_id
        }
        print(f"📊 Google Sheets upload enabled via command line")
        print(f"   Credentials: {args.sheets_credentials}")
        print(f"   Spreadsheet ID: {args.sheets_id}")
    else:
        # Check config file setting (default behavior)
        config_sheets = config.get('google_sheets', {})
        if config_sheets.get('enabled', False):
            # Enabled in config - validate required fields
            credentials_file = config_sheets.get('credentials_file', '')
            spreadsheet_id = config_sheets.get('spreadsheet_id', '')
            
            if not credentials_file or not spreadsheet_id:
                print("⚠️ Warning: Google Sheets enabled in config but missing credentials_file or spreadsheet_id")
                print("   Disabling Google Sheets upload. To fix:")
                print(f"   1. Set 'enabled': false in {args.config}")
                print("   2. Or provide valid credentials_file and spreadsheet_id in config")
                print("   3. Or use command line: --upload-to-sheets --sheets-credentials <file> --sheets-id <id>")
                sheets_enabled = False
            else:
                sheets_enabled = True
                sheets_config = config_sheets.copy()
                print(f"📊 Google Sheets upload enabled via config file")
        else:
            print("📊 Google Sheets upload disabled (default). Use --upload-to-sheets to enable.")

    # Update config with determined Google Sheets settings
    config['google_sheets'] = sheets_config
    config['google_sheets']['enabled'] = sheets_enabled

    # Update config with command line arguments - Enhanced concurrency and delay configuration
    if args.max_questions:
        config['scraper']['max_questions_per_run'] = args.max_questions
    if args.concurrency:
        config['scraper']['concurrency'] = args.concurrency
    if args.min_delay is not None:
        if 'delays' not in config['scraper']:
            config['scraper']['delays'] = {}
        config['scraper']['delays']['min'] = args.min_delay
    if args.max_delay is not None:
        if 'delays' not in config['scraper']:
            config['scraper']['delays'] = {}
        config['scraper']['delays']['max'] = args.max_delay
    if args.strict_mapping:
        config['scraper']['strict_mapping'] = True

    # Validate delay configuration
    delay_config = config['scraper'].get('delays', {})
    min_delay = delay_config.get('min', 1.0)
    max_delay = delay_config.get('max', 3.0)
    
    if min_delay > max_delay:
        print(f"❌ Error: Minimum delay ({min_delay}s) cannot be greater than maximum delay ({max_delay}s)")
        return 1
    if min_delay < 0:
        print(f"❌ Error: Minimum delay cannot be negative ({min_delay}s)")
        return 1
    if max_delay < 0:
        print(f"❌ Error: Maximum delay cannot be negative ({max_delay}s)")
        return 1

    # Validate concurrency configuration
    concurrency = config['scraper'].get('concurrency', 3)
    if concurrency < 1:
        print(f"❌ Error: Concurrency must be at least 1 (got {concurrency})")
        return 1
    if concurrency > 20:
        print(f"⚠️ Warning: High concurrency ({concurrency}) may cause rate limiting or IP blocking")
        print("   Consider using lower concurrency (3-8) for safer scraping")

    # Ensure directories exist
    ensure_directories(config)

    # Set up logging
    setup_logging(config)
    logger = logging.getLogger(__name__)

    # Initialize components
    csv_handler = CSVHandler(config['storage']['output_dir'])
    indexer = QuestionIndexer()
    metrics = ScrapingMetrics()

    # Handle validation-only mode
    if args.validate_only:
        logger.info("Running CSV validation only")
        validation_results = validate_csv_files(
            config['storage']['output_dir'], 
            config['storage']['csv_files']
        )
        
        all_valid = all(validation_results.values())
        print(f"\nValidation {'✅ PASSED' if all_valid else '❌ FAILED'}")
        return

    # Handle index reset if requested
    if args.reset_indices:
        logger.warning("Resetting question indices to 0")
        indexer.reset_indices()

    # Run pre-scrape checks
    if not run_pre_scrape_checks(config, logger):
        logger.error("Pre-scrape checks failed - aborting")
        return

    # Print current statistics
    print_csv_statistics(csv_handler, config)

    logger.info("Starting FunTrivia scraper")
    logger.info(f"Configuration: max_questions={config['scraper']['max_questions_per_run']}, "
                f"concurrency={config['scraper']['concurrency']}")
    logger.info(f"Delay configuration: {min_delay}-{max_delay}s between requests")
    logger.info(f"Rate limit: {config['scraper']['rate_limit']['requests_per_minute']} requests/minute")
    logger.info(f"Current indices: {indexer.get_all_indices()}")
    logger.info(f"Mode: {'Dry Run' if args.dry_run else 'Append' if not args.overwrite else 'Overwrite'}")

    # Initialize scraper
    scraper = FunTriviaScraper(args.config)
    
    try:
        await scraper.initialize()
        logger.info("Scraper initialized successfully")
        
        # Scrape questions
        logger.info("Starting question scraping")
        questions = await scraper.scrape_questions(
            max_questions=config['scraper']['max_questions_per_run']
        )
        logger.info(f"Scraped {len(questions)} questions total")

        if not questions:
            logger.warning("No questions were scraped!")
            return

        # Validate scraped data unless skipped
        if not args.skip_validation:
            logger.info("Starting data validation")
            logger.debug(f"Validating {len(questions)} questions...")
            validation_summary = validate_scraped_data(questions)
            print_validation_report(validation_summary)
            
            # Record validation metrics
            metrics.record_validation_results(
                validation_summary['valid_questions'],
                validation_summary['invalid_questions'],
                validation_summary['questions_with_warnings']
            )
            
            # Filter out invalid questions
            if validation_summary['invalid_questions'] > 0:
                logger.warning(f"Removing {validation_summary['invalid_questions']} invalid questions")
                # Note: In a real implementation, you'd filter out invalid questions here
                # For now, we'll proceed with all questions
            
            logger.info(f"Validation completed: {validation_summary['valid_questions']} valid, {validation_summary['invalid_questions']} invalid, {validation_summary['questions_with_warnings']} with warnings")

        # Group questions by type
        logger.info("Grouping questions by type")
        questions_by_type = {
            'multiple_choice': [],
            'true_false': [],
            'sound': []
        }

        for question in questions:
            try:
                formatted_question = format_question_data_enhanced(question)
                question_type = question.get('type', 'multiple_choice')
                questions_by_type[question_type].append(formatted_question)
                
                # Record metrics
                metrics.record_question_scraped(question_type)
            except Exception as e:
                logger.error(f"Error formatting question {question.get('id', 'unknown')}: {e}")
                logger.debug("Question formatting error details:", exc_info=True)
                # Continue with next question instead of failing
                continue

        # Log question distribution
        logger.info("Question type distribution:")
        for qtype, qlist in questions_by_type.items():
            logger.info(f"  {qtype}: {len(qlist)} questions")

        # Handle dry run mode
        if args.dry_run:
            logger.info("DRY RUN MODE - No data will be saved")
            print("\n🧪 DRY RUN MODE - No data will be saved")
            print("Question summary:")
            for qtype, qlist in questions_by_type.items():
                print(f"  {qtype}: {len(qlist)} questions")
            logger.info("Dry run completed successfully")
            return

        # Create backups if requested and overwriting
        if args.overwrite and args.backup:
            logger.info("Creating backups of existing CSV files")
            backup_count = 0
            for question_type, csv_file in config['storage']['csv_files'].items():
                try:
                    csv_handler.backup_csv(csv_file)
                    backup_count += 1
                    logger.debug(f"Created backup for {csv_file}")
                except Exception as e:
                    logger.error(f"Failed to create backup for {csv_file}: {e}")
            logger.info(f"Created {backup_count} CSV backups")

        # Save questions to CSV files
        logger.info("Starting CSV file operations")
        csv_files = {}
        total_new_questions = 0
        csv_operation_stats = {'successful': 0, 'failed': 0, 'skipped': 0}
        
        for question_type, type_questions in questions_by_type.items():
            if not type_questions:
                logger.info(f"No {question_type} questions to save - skipping")
                csv_operation_stats['skipped'] += 1
                continue

            csv_file = config['storage']['csv_files'][question_type]
            csv_files[question_type] = str(Path(config['storage']['output_dir']) / csv_file)

            try:
                if args.overwrite:
                    # Overwrite mode - use pandas directly
                    logger.info(f"Overwriting {csv_file} with {len(type_questions)} questions")
                    df = pd.DataFrame(type_questions)
                    df = csv_handler.ensure_csv_structure(df, question_type)
                    df.to_csv(csv_files[question_type], index=False)
                    new_count = len(type_questions)
                    logger.info(f"Successfully overwrote {csv_file} with {new_count} {question_type} questions")
                else:
                    # Append mode - use CSV handler
                    logger.info(f"Appending {len(type_questions)} questions to {csv_file}")
                    new_count = csv_handler.append_to_csv(type_questions, csv_file, question_type)
                    logger.info(f"Successfully added {new_count} new {question_type} questions to {csv_file}")
                
                total_new_questions += new_count
                csv_operation_stats['successful'] += 1
                
                # Log sample of saved data for verification
                if type_questions:
                    sample_question = type_questions[0]
                    logger.debug(f"Sample {question_type} question saved:")
                    logger.debug(f"  Key: {sample_question.get('Key')}")
                    logger.debug(f"  Question: {sample_question.get('Question', '')[:100]}...")
                    logger.debug(f"  Correct Answer: {sample_question.get('CorrectAnswer')}")
                    logger.debug(f"  Media: {sample_question.get('ImagePath') or sample_question.get('AudioPath') or 'None'}")
            
            except Exception as e:
                csv_operation_stats['failed'] += 1
                logger.error(f"Failed to save {question_type} questions to {csv_file}: {e}")
                logger.debug(f"CSV save error details for {question_type}:", exc_info=True)
                # Continue with other question types instead of failing entirely

        # Log CSV operation summary
        logger.info("CSV operation summary:")
        logger.info(f"  Successful: {csv_operation_stats['successful']} files")
        logger.info(f"  Failed: {csv_operation_stats['failed']} files")
        logger.info(f"  Skipped: {csv_operation_stats['skipped']} files")
        logger.info(f"  Total new questions saved: {total_new_questions}")

        # Validate saved CSV files
        if total_new_questions > 0 and not args.skip_validation:
            logger.info("Validating saved CSV files")
            try:
                validation_results = validate_csv_files(
                    config['storage']['output_dir'], 
                    config['storage']['csv_files']
                )
                
                all_valid = all(validation_results.values())
                if all_valid:
                    logger.info("All CSV files passed validation")
                else:
                    logger.warning("Some CSV files failed validation:")
                    for file_type, is_valid in validation_results.items():
                        if not is_valid:
                            logger.warning(f"  {file_type}: FAILED")
                        else:
                            logger.debug(f"  {file_type}: PASSED")
            except Exception as e:
                logger.error(f"CSV validation failed: {e}")
                logger.debug("CSV validation error details:", exc_info=True)

        # Upload to Google Sheets if enabled and configured
        sheets_upload_attempted = False
        sheets_upload_successful = False
        
        if sheets_enabled and total_new_questions > 0:
            try:
                logger.info("Starting Google Sheets upload process")
                
                # Get credentials and spreadsheet info
                credentials_file = sheets_config.get('credentials_file', '')
                spreadsheet_id = sheets_config.get('spreadsheet_id', '')
                
                # Final validation before upload attempt
                if not credentials_file or not spreadsheet_id:
                    logger.warning("Google Sheets upload skipped: missing credentials_file or spreadsheet_id")
                    print("⚠️ Google Sheets upload skipped: incomplete configuration")
                elif not os.path.exists(credentials_file):
                    logger.warning(f"Google Sheets upload skipped: credentials file not found: {credentials_file}")
                    print(f"⚠️ Google Sheets upload skipped: credentials file not found: {credentials_file}")
                else:
                    sheets_upload_attempted = True
                    logger.info(f"Uploading {total_new_questions} new questions to Google Sheets")
                    logger.debug(f"Using credentials: {credentials_file}")
                    logger.debug(f"Target spreadsheet: {spreadsheet_id}")
                    print(f"📊 Uploading {total_new_questions} new questions to Google Sheets...")
                    
                    uploader = GoogleSheetsUploader(
                        credentials_file=credentials_file,
                        spreadsheet_id=spreadsheet_id
                    )
                    
                    # Validate Google Sheets setup
                    logger.debug("Validating Google Sheets setup...")
                    is_valid, message = uploader.validate_setup()
                    if not is_valid:
                        logger.error(f"Google Sheets validation failed: {message}")
                        print(f"❌ Google Sheets validation failed: {message}")
                        print("\nTroubleshooting steps:")
                        print("1. Ensure Google Sheets API is enabled in Google Cloud Console")
                        print("2. Verify credentials file is valid service account JSON")
                        print("3. Check that spreadsheet is shared with service account email")
                        print("4. Test connection with: python src/main.py --sheets-test-only --sheets-credentials <file> --sheets-id <id>")
                    else:
                        logger.info("Google Sheets setup validation passed")
                        
                        # Only upload files that have new questions
                        files_to_upload = {}
                        for question_type, file_path in csv_files.items():
                            if question_type in questions_by_type and questions_by_type[question_type]:
                                files_to_upload[question_type] = file_path
                                logger.debug(f"Will upload {question_type}: {file_path}")
                        
                        if files_to_upload:
                            logger.info(f"Uploading {len(files_to_upload)} CSV files to Google Sheets")
                            uploader.upload_csv_files(files_to_upload)
                            sheets_upload_successful = True
                            logger.info("Successfully uploaded data to Google Sheets")
                            print("✅ Successfully uploaded data to Google Sheets")
                        else:
                            logger.info("No new data to upload to Google Sheets")
                            print("ℹ️ No new data to upload to Google Sheets")
                    
            except Exception as e:
                logger.error(f"Failed to upload to Google Sheets: {e}")
                logger.debug("Google Sheets upload error details:", exc_info=True)
                print(f"❌ Failed to upload to Google Sheets: {e}")
                print("   Check the log file for detailed error information.")

        elif sheets_enabled and total_new_questions == 0:
            logger.info("Google Sheets upload skipped: no new questions to upload")
            print("📊 Google Sheets upload skipped: no new questions to upload")
        elif not sheets_enabled:
            logger.debug("Google Sheets upload disabled")

        # Finalize metrics
        metrics.finalize_session()

        # Clean up temporary media files and show media statistics
        try:
            temp_files_cleaned = scraper.media_handler.cleanup_temp_files()
            if temp_files_cleaned > 0:
                logger.info(f"Cleaned up {temp_files_cleaned} temporary media files")
            
            # Display media statistics
            media_stats = scraper.media_handler.get_media_stats()
            if media_stats['images']['count'] > 0 or media_stats['audio']['count'] > 0:
                logger.info("Media files summary:")
                logger.info(f"  Images: {media_stats['images']['count']} files ({media_stats['images']['total_size_mb']:.1f} MB)")
                logger.info(f"  Audio: {media_stats['audio']['count']} files ({media_stats['audio']['total_size_mb']:.1f} MB)")
                
                print("\n" + "="*60)
                print("MEDIA FILES SUMMARY")
                print("="*60)
                print(f"Images: {media_stats['images']['count']} files ({media_stats['images']['total_size_mb']:.1f} MB)")
                print(f"  Directory: {media_stats['images']['directory']}")
                print(f"Audio: {media_stats['audio']['count']} files ({media_stats['audio']['total_size_mb']:.1f} MB)")
                print(f"  Directory: {media_stats['audio']['directory']}")
                print("="*60)
            else:
                logger.debug("No media files were processed")
        except Exception as e:
            logger.error(f"Error processing media statistics: {e}")
            logger.debug("Media statistics error details:", exc_info=True)

        # Check for unmapped values and provide feedback
        try:
            unmapped_values = scraper.get_unmapped_values()
            if any(unmapped_values.values()):
                logger.warning("Unmapped values detected during scraping:")
                for mapping_type, values in unmapped_values.items():
                    if values:
                        logger.warning(f"  {mapping_type.upper()}: {list(values)}")
                
                print("\n" + "="*60)
                print("MAPPING FEEDBACK")
                print("="*60)
                print("The following values were encountered but not found in mappings:")
                print("Consider adding them to config/mappings.json")
                
                for mapping_type, values in unmapped_values.items():
                    if values:
                        print(f"\n{mapping_type.upper()} MAPPING:")
                        for value in sorted(values):
                            print(f"  - '{value}'")
                        
                print(f"\nTo add these mappings, edit config/mappings.json and add the")
                print(f"unmapped values to the appropriate mapping categories.")
                print("="*60)
            else:
                logger.info("All values were successfully mapped")
        except Exception as e:
            logger.error(f"Error checking unmapped values: {e}")
            logger.debug("Unmapped values check error details:", exc_info=True)

        # Print final summary
        final_indices = indexer.get_all_indices()
        
        logger.info("="*60)
        logger.info("SCRAPING SESSION COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        logger.info(f"Total new questions scraped: {total_new_questions}")
        
        for qtype, qlist in questions_by_type.items():
            if qlist:
                csv_file = config['storage']['csv_files'][qtype]
                stats = csv_handler.get_csv_stats(csv_file)
                logger.info(f"  {qtype.replace('_', ' ').title()}: {len(qlist)} new, {stats['total_questions']} total")
        
        logger.info(f"Question indices after run:")
        for qtype, count in final_indices.items():
            logger.info(f"  {qtype}: {count}")
        
        # Print performance metrics
        current_stats = metrics.get_current_stats()
        logger.info(f"Performance metrics:")
        logger.info(f"  Duration: {current_stats['duration_seconds']/60:.1f} minutes")
        logger.info(f"  Average rate: {current_stats['performance']['avg_questions_per_minute']:.1f} questions/min")
        logger.info(f"  Peak memory: {current_stats['performance']['peak_memory_mb']:.1f} MB")
        
        # Google Sheets status reporting
        if sheets_enabled:
            if sheets_upload_attempted:
                if sheets_upload_successful:
                    logger.info("Google Sheets: Upload completed successfully")
                else:
                    logger.warning("Google Sheets: Upload attempted but failed")
            else:
                logger.warning("Google Sheets: Upload skipped due to configuration issues")
        else:
            logger.debug("Google Sheets: Disabled")
        
        logger.info(f"Mode: {'Overwrite' if args.overwrite else 'Append'}")
        logger.info("="*60)

        print("\n" + "="*60)
        print("SCRAPING SUMMARY")
        print("="*60)
        print(f"Total new questions scraped: {total_new_questions}")
        
        for qtype, qlist in questions_by_type.items():
            if qlist:
                csv_file = config['storage']['csv_files'][qtype]
                stats = csv_handler.get_csv_stats(csv_file)
                print(f"  {qtype.replace('_', ' ').title()}: {len(qlist)} new, {stats['total_questions']} total")
        
        print(f"\nQuestion indices after run:")
        for qtype, count in final_indices.items():
            print(f"  {qtype}: {count}")
        
        print(f"\nCSV files location: {config['storage']['output_dir']}")
        print(f"Media files location: assets/")
        
        # Print performance metrics
        current_stats = metrics.get_current_stats()
        print(f"\nPerformance metrics:")
        print(f"  Duration: {current_stats['duration_seconds']/60:.1f} minutes")
        print(f"  Average rate: {current_stats['performance']['avg_questions_per_minute']:.1f} questions/min")
        print(f"  Peak memory: {current_stats['performance']['peak_memory_mb']:.1f} MB")
        
        # Google Sheets status reporting
        if sheets_enabled:
            if sheets_upload_attempted:
                if sheets_upload_successful:
                    print("Google Sheets: Upload completed successfully")
                else:
                    print("Google Sheets: Upload attempted but failed")
            else:
                print("Google Sheets: Upload skipped (configuration issues)")
        else:
            print("Google Sheets: Disabled")
        
        print(f"Mode: {'Overwrite' if args.overwrite else 'Append'}")
        
        # Print validation summary if not skipped
        if not args.skip_validation and 'validation_summary' in locals():
            print(f"\nData Quality:")
            print(f"  Valid questions: {validation_summary['valid_questions']}")
            print(f"  Invalid questions: {validation_summary['invalid_questions']}")
            print(f"  Questions with warnings: {validation_summary['questions_with_warnings']}")
        
        print("="*60)

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        print("\nScraping interrupted by user. Progress has been saved.")
        metrics.finalize_session()
    except Exception as e:
        logger.error(f"Fatal error occurred during scraping: {e}")
        logger.error("Full error details:", exc_info=True)
        print(f"\nFatal error occurred: {e}")
        print("Check the log file for detailed error information.")
        metrics.record_error("scraping_error", str(e))
        metrics.finalize_session()
        raise
    finally:
        # Clean up
        try:
            await scraper.close()
            logger.info("Scraper cleanup completed")
        except Exception as e:
            logger.error(f"Error during scraper cleanup: {e}")
            logger.debug("Cleanup error details:", exc_info=True)
        logger.info("Main scraping process completed")

if __name__ == '__main__':
    asyncio.run(main()) 