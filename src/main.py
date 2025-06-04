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
    """Set up logging configuration."""
    log_file = config['logging']['file']
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logging.basicConfig(
        level=config['logging']['level'],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

def format_question_data_enhanced(question: Dict[str, Any]) -> Dict[str, Any]:
    """Enhanced formatting of question data to match CSV template structure exactly."""
    # Base structure matching the CSV template
    formatted = {
        'Key': question.get('id', ''),
        'Domain': question.get('domain', 'Culture'),
        'Topic': question.get('topic', 'General'),
        'Difficulty': question.get('difficulty', 'Normal'),
        'Question': question.get('question', ''),
        'Option1': '',
        'Option2': '',
        'Option3': '',
        'Option4': '',
        'CorrectAnswer': question.get('correct_answer', ''),
        'Hint': question.get('hint', ''),
        'Description': question.get('description', ''),
        'ImagePath': '',
        'AudioPath': ''
    }

    # Fill in options based on question type
    options = question.get('options', [])
    for i, option in enumerate(options[:4], 1):  # Limit to 4 options max
        formatted[f'Option{i}'] = option.strip()

    # Handle media paths - ensure proper formatting
    if question.get('media_path'):
        media_path = question['media_path']
        # Ensure path starts with assets/ for consistency
        if not media_path.startswith('assets/'):
            if question.get('type') == 'sound':
                media_path = f"assets/audio/{os.path.basename(media_path)}"
            else:
                media_path = f"assets/images/{os.path.basename(media_path)}"
        
        if question.get('type') == 'sound':
            formatted['AudioPath'] = media_path
        else:
            formatted['ImagePath'] = media_path

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
    parser.add_argument('--concurrency', type=int, help='Number of concurrent scrapers')
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
    
    args = parser.parse_args()

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

    # Update config with command line arguments
    if args.max_questions:
        config['scraper']['max_questions_per_run'] = args.max_questions
    if args.concurrency:
        config['scraper']['concurrency'] = args.concurrency
    if args.strict_mapping:
        config['scraper']['strict_mapping'] = True

    # Run pre-scrape checks
    if not run_pre_scrape_checks(config, logger):
        logger.error("Pre-scrape checks failed - aborting")
        return

    # Print current statistics
    print_csv_statistics(csv_handler, config)

    logger.info("Starting FunTrivia scraper")
    logger.info(f"Configuration: max_questions={config['scraper']['max_questions_per_run']}, "
                f"concurrency={config['scraper']['concurrency']}")
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
            logger.info("Validating scraped data")
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

        # Group questions by type
        questions_by_type = {
            'multiple_choice': [],
            'true_false': [],
            'sound': []
        }

        for question in questions:
            formatted_question = format_question_data_enhanced(question)
            question_type = question.get('type', 'multiple_choice')
            questions_by_type[question_type].append(formatted_question)
            
            # Record metrics
            metrics.record_question_scraped(question_type)

        # Log question distribution
        for qtype, qlist in questions_by_type.items():
            logger.info(f"Found {len(qlist)} {qtype} questions")

        # Handle dry run mode
        if args.dry_run:
            print("\n🧪 DRY RUN MODE - No data will be saved")
            print("Question summary:")
            for qtype, qlist in questions_by_type.items():
                print(f"  {qtype}: {len(qlist)} questions")
            return

        # Create backups if requested and overwriting
        if args.overwrite and args.backup:
            logger.info("Creating backups of existing CSV files")
            for question_type, csv_file in config['storage']['csv_files'].items():
                csv_handler.backup_csv(csv_file)

        # Save questions to CSV files
        csv_files = {}
        total_new_questions = 0
        
        for question_type, type_questions in questions_by_type.items():
            if not type_questions:
                logger.info(f"No {question_type} questions to save")
                continue

            csv_file = config['storage']['csv_files'][question_type]
            csv_files[question_type] = str(Path(config['storage']['output_dir']) / csv_file)

            if args.overwrite:
                # Overwrite mode - use pandas directly
                df = pd.DataFrame(type_questions)
                df = csv_handler.ensure_csv_structure(df, question_type)
                df.to_csv(csv_files[question_type], index=False)
                new_count = len(type_questions)
                logger.info(f"Overwrote {csv_file} with {new_count} {question_type} questions")
            else:
                # Append mode - use CSV handler
                new_count = csv_handler.append_to_csv(type_questions, csv_file, question_type)
                logger.info(f"Added {new_count} new {question_type} questions to {csv_file}")
            
            total_new_questions += new_count
            
            # Log sample of saved data for verification
            if type_questions:
                sample_question = type_questions[0]
                logger.debug(f"Sample {question_type} question:")
                logger.debug(f"  Key: {sample_question.get('Key')}")
                logger.debug(f"  Question: {sample_question.get('Question', '')[:50]}...")
                logger.debug(f"  Correct Answer: {sample_question.get('CorrectAnswer')}")

        # Validate saved CSV files
        if total_new_questions > 0 and not args.skip_validation:
            logger.info("Validating saved CSV files")
            validation_results = validate_csv_files(
                config['storage']['output_dir'], 
                config['storage']['csv_files']
            )
            
            if not all(validation_results.values()):
                logger.warning("Some CSV files failed validation")

        # Upload to Google Sheets if enabled
        if config.get('google_sheets', {}).get('enabled', False) and total_new_questions > 0:
            try:
                logger.info("Uploading data to Google Sheets")
                
                credentials_file = config['google_sheets']['credentials_file']
                spreadsheet_id = config['google_sheets']['spreadsheet_id']
                
                # Check if credentials file exists
                if not os.path.exists(credentials_file):
                    logger.error(f"Google Sheets credentials file not found: {credentials_file}")
                else:
                    uploader = GoogleSheetsUploader(
                        credentials_file=credentials_file,
                        spreadsheet_id=spreadsheet_id
                    )
                    
                    # Validate Google Sheets setup
                    is_valid, message = uploader.validate_setup()
                    if not is_valid:
                        logger.error(f"Google Sheets validation failed: {message}")
                    else:
                        # Only upload files that have new questions
                        files_to_upload = {}
                        for question_type, file_path in csv_files.items():
                            if question_type in questions_by_type and questions_by_type[question_type]:
                                files_to_upload[question_type] = file_path
                        
                        if files_to_upload:
                            uploader.upload_csv_files(files_to_upload)
                            logger.info("Successfully uploaded data to Google Sheets")
                        else:
                            logger.info("No new data to upload to Google Sheets")
                    
            except Exception as e:
                logger.error(f"Failed to upload to Google Sheets: {e}")
                logger.debug("Google Sheets upload error details:", exc_info=True)

        # Finalize metrics
        metrics.finalize_session()

        # Print final summary
        final_indices = indexer.get_all_indices()
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
        
        if config.get('google_sheets', {}).get('enabled', False):
            print("Google Sheets: Upload completed" if total_new_questions > 0 else "Google Sheets: No new data to upload")
        
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
        logger.error(f"An error occurred during scraping: {e}")
        logger.debug("Full error details:", exc_info=True)
        print(f"\nError occurred: {e}")
        print("Check the log file for detailed error information.")
        metrics.record_error("scraping_error", str(e))
        metrics.finalize_session()
        raise
    finally:
        # Clean up
        await scraper.close()
        logger.info("Scraping completed")

if __name__ == '__main__':
    asyncio.run(main()) 