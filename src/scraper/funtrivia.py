import asyncio
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import re
import logging
import random
import sys
import os
from playwright.async_api import Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type # type: ignore

# Add the src directory to the path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scraper.base import BaseScraper
from scraper.config import ScraperConfig
from scraper.media import MediaHandler, MediaReference
from utils.rate_limiter import RateLimiter
from utils.indexing import QuestionIndexer
from utils.question_classifier import QuestionClassifier
from utils.text_processor import TextProcessor
from constants import (
    TIMEOUTS, USER_AGENTS, DESCRIPTION_SELECTORS, 
    THRESHOLDS, DEFAULT_PATHS
)


class FunTriviaScraper(BaseScraper):
    """
    Enhanced FunTrivia scraper with improved question type detection,
    description extraction, and organized modular structure.
    """
    
    def __init__(self, config_path: str = None, speed_profile: str = "normal"):
        config_path = config_path or DEFAULT_PATHS['config_file']
        super().__init__(config_path)
        
        # Initialize centralized configuration and mapping handler
        # This replaces the old _load_mappings approach with centralized config management
        mappings_file = DEFAULT_PATHS['mappings_file']
        self.scraper_config = ScraperConfig(mappings_file)
        
        # Initialize media handler for proper file management
        self.media_handler = MediaHandler(self.config)
        
        # Initialize other components
        self.indexer = QuestionIndexer()
        self.rate_limiter = RateLimiter(
            self.config['scraper']['rate_limit']['requests_per_minute']
        )
        self.question_classifier = QuestionClassifier()
        self.text_processor = TextProcessor()
        
        # Configuration
        self.strict_mapping = self.config.get('scraper', {}).get('strict_mapping', False)
        
        # Initialize incremental saving - this will save questions immediately after each quiz
        self.incremental_save = True  # Enable incremental saving by default
        self.csv_handler = None  # Will be initialized when needed
        
        # SPEED OPTIMIZATION: Load speed profile
        self.speed_profile = speed_profile
        self._load_speed_profile()
        
        # Performance tracking
        self.performance_stats = {
            'start_time': None,
            'quizzes_per_minute': 0,
            'questions_per_minute': 0,
            'errors_encountered': 0,
            'consecutive_failures': 0
        }

    def _load_speed_profile(self):
        """Load speed optimization settings based on selected profile."""
        try:
            import json
            with open('config/speed_profiles.json', 'r') as f:
                profiles = json.load(f)
            
            profile_config = profiles['speed_profiles'].get(self.speed_profile, profiles['speed_profiles']['normal'])
            
            # Apply speed profile to scraper configuration
            self.config['scraper']['concurrency'] = profile_config['concurrency']
            self.config['scraper']['delays'] = profile_config['delays']
            self.config['scraper']['rate_limit'] = profile_config['rate_limit']
            self.config['scraper']['timeouts'] = profile_config['timeouts']
            
            # Speed-specific settings
            self.wait_for_networkidle = profile_config.get('wait_for_networkidle', True)
            self.parallel_media_downloads = profile_config.get('parallel_media_downloads', True)
            self.fast_fail_timeout = profile_config.get('fast_fail_timeout', 25000)
            
            # Performance optimizations
            optimizations = profiles.get('performance_optimizations', {})
            self.batch_process_questions = optimizations.get('batch_process_questions', True)
            self.parallel_result_extraction = optimizations.get('parallel_result_extraction', True)
            
            # Fast radio button selection - check profile-specific setting first, then global
            self.fast_radio_button_selection = profile_config.get('fast_radio_button_selection', 
                                                                 optimizations.get('fast_radio_button_selection', False))
            self.optimized_selectors = optimizations.get('optimized_selectors', True)
            
            # Safety features
            safety = profiles.get('safety_features', {})
            self.auto_slowdown_on_errors = safety.get('auto_slowdown_on_errors', True)
            self.max_consecutive_failures = safety.get('max_consecutive_failures', 5)
            self.error_backoff_multiplier = safety.get('error_backoff_multiplier', 2.0)
            
            # Update rate limiter with new settings
            self.rate_limiter = RateLimiter(
                self.config['scraper']['rate_limit']['requests_per_minute']
            )
            
            self.logger.info(f"Speed profile loaded: {self.speed_profile} - {profile_config['description']}")
            self.logger.info(f"Performance settings: {profile_config['concurrency']} concurrent, "
                           f"{profile_config['delays']['min']}-{profile_config['delays']['max']}s delays, "
                           f"{profile_config['rate_limit']['requests_per_minute']} req/min")
            
        except Exception as e:
            self.logger.warning(f"Failed to load speed profile: {e}. Using default settings.")
            self.speed_profile = "normal"

    async def initialize(self) -> None:
        """Initialize the scraper with a browser instance."""
        try:
            from playwright.async_api import async_playwright # type: ignore
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            self._ensure_directories()
            
            # Initialize CSV handler for incremental saving
            if self.incremental_save:
                from utils.csv_handler import CSVHandler
                self.csv_handler = CSVHandler(self.config['storage']['output_dir'])
                self.logger.info("Incremental saving enabled - questions will be saved after each quiz")
            
            self.logger.info("Scraper initialized successfully")
            self.logger.info(f"Current question indices: {self.indexer.get_all_indices()}")
        except Exception as e:
            self.logger.error(f"Failed to initialize scraper: {e}")
            raise

    async def close(self) -> None:
        """Close the browser instance."""
        if self.browser:
            try:
                await self.browser.close()
                self.logger.info("Browser closed successfully")
                self.logger.info(f"Final question indices: {self.indexer.get_all_indices()}")
            except Exception as e:
                self.logger.error(f"Error closing browser: {e}")

    async def scrape_questions(self, max_questions: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scrape questions from FunTrivia.com with comprehensive logging and incremental saving."""
        if not self.browser:
            await self.initialize()

        questions = []  # This will track all questions for summary, but they're saved incrementally
        scraping_stats = {
            'categories_processed': 0,
            'categories_failed': 0,
            'quizzes_processed': 0,
            'quizzes_failed': 0,
            'questions_extracted': 0,
            'questions_saved': 0,  # Track questions actually saved to files
            'questions_by_type': {'multiple_choice': 0, 'true_false': 0, 'sound': 0},
            'media_downloads': {'attempted': 0, 'successful': 0, 'failed': 0},
            'mapping_issues': {'domain': set(), 'topic': set(), 'difficulty': set()}
        }
        
        try:
            self.logger.info("="*60)
            self.logger.info("STARTING FUNTIVIA SCRAPING SESSION")
            self.logger.info("="*60)
            self.logger.info(f"Target: {max_questions if max_questions else 'unlimited'} questions")
            self.logger.info(f"Speed Profile: {self.speed_profile.upper()}")
            self.logger.info(f"Configuration: {self.config['scraper']['concurrency']} concurrent browsers")
            self.logger.info(f"Delay range: {self.config['scraper']['delays']['min']}-{self.config['scraper']['delays']['max']}s")
            self.logger.info(f"Rate limit: {self.config['scraper']['rate_limit']['requests_per_minute']} requests/minute")
            self.logger.info(f"Network wait: {'ENABLED' if self.wait_for_networkidle else 'DISABLED (faster)'}")
            self.logger.info(f"Incremental saving: {'ENABLED' if self.incremental_save else 'DISABLED'} - questions {'will be saved immediately' if self.incremental_save else 'saved at end'}")
            
            # Start performance tracking
            import time
            self.performance_stats['start_time'] = time.time()
            
            categories = await self._get_categories()
            self.logger.info(f"Discovered {len(categories)} categories for processing")
            
            # Process categories concurrently with detailed logging
            questions = await self._process_categories_concurrently(categories, max_questions, scraping_stats)
            
            # Log final statistics
            self._log_scraping_summary(scraping_stats, questions)
            
            return questions
            
        except Exception as e:
            self.logger.error(f"Fatal error during question scraping: {e}")
            self.logger.error("Stack trace:", exc_info=True)
            # Log partial results before re-raising
            if questions:
                self.logger.warning(f"Partial results available: {len(questions)} questions scraped before error")
                self._log_scraping_summary(scraping_stats, questions)
            raise

    async def _process_categories_concurrently(self, categories: List[str], max_questions: Optional[int], stats: Dict) -> List[Dict[str, Any]]:
        """Process categories concurrently with detailed logging and error handling."""
        questions = []
        semaphore = asyncio.Semaphore(self.config['scraper']['concurrency'])
        
        async def scrape_category(category: str) -> List[Dict[str, Any]]:
            async with semaphore:
                category_stats = {'quizzes_attempted': 0, 'quizzes_successful': 0, 'questions_found': 0}
                
                try:
                    self.logger.info(f"Processing category: {category}")
                    stats['categories_processed'] += 1
                    
                    quiz_links = await self._get_quiz_links(category)
                    self.logger.info(f"Found {len(quiz_links)} quizzes in category {category}")
                    
                    category_questions = []
                    for quiz_link in quiz_links:
                        if max_questions and len(questions) >= max_questions:
                            self.logger.info(f"Reached maximum questions limit ({max_questions}), stopping category processing")
                            break
                        
                        category_stats['quizzes_attempted'] += 1
                        stats['quizzes_processed'] += 1
                        
                        try:
                            async with self.rate_limiter:
                                quiz_questions = await self._scrape_quiz(quiz_link, stats)
                                if quiz_questions:
                                    category_questions.extend(quiz_questions)
                                    category_stats['quizzes_successful'] += 1
                                    category_stats['questions_found'] += len(quiz_questions)
                                    
                                    # Track questions that were saved (if incremental saving is enabled)
                                    if self.incremental_save:
                                        stats['questions_saved'] += len(quiz_questions)
                                    
                                    self.logger.debug(f"Quiz successful: {len(quiz_questions)} questions from {quiz_link}")
                                else:
                                    self.logger.warning(f"No questions extracted from quiz: {quiz_link}")
                                
                                await self._random_delay()
                        
                        except Exception as quiz_error:
                            stats['quizzes_failed'] += 1
                            self.logger.error(f"Failed to scrape quiz {quiz_link}: {quiz_error}")
                            self.logger.debug("Quiz scraping error details:", exc_info=True)
                            # Continue with next quiz instead of failing the entire category
                            continue
                    
                    # Log category completion statistics
                    success_rate = (category_stats['quizzes_successful'] / category_stats['quizzes_attempted']) * 100 if category_stats['quizzes_attempted'] > 0 else 0
                    self.logger.info(f"Category '{category}' completed: {category_stats['questions_found']} questions from {category_stats['quizzes_successful']}/{category_stats['quizzes_attempted']} quizzes ({success_rate:.1f}% success rate)")
                    
                    return category_questions
                    
                except Exception as e:
                    stats['categories_failed'] += 1
                    self.logger.error(f"Category processing failed for {category}: {e}")
                    self.logger.debug("Category processing error details:", exc_info=True)
                    return []

        # Execute concurrent scraping with progress logging
        self.logger.info(f"Starting concurrent processing of {len(categories)} categories with {self.config['scraper']['concurrency']} workers")
        
        tasks = [scrape_category(category) for category in categories]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Category {i+1} failed with exception: {result}")
                self.logger.debug("Category exception details:", exc_info=True)
                continue
            
            questions.extend(result)
            if max_questions and len(questions) >= max_questions:
                questions = questions[:max_questions]
                self.logger.info(f"Trimmed results to maximum {max_questions} questions")
                break

        return questions

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((PlaywrightTimeoutError,))
    )
    async def _scrape_quiz(self, quiz_url: str, stats: Dict = None) -> List[Dict[str, Any]]:
        """
        Comprehensive quiz scraper with detailed logging at each step.
        """
        context = await self.browser.new_context(user_agent=self._get_random_user_agent())
        page = await context.new_page()
        
        quiz_log_id = quiz_url.split('/')[-1][:30]  # Short identifier for logging
        
        try:
            self.logger.debug(f"[{quiz_log_id}] Starting quiz scraping process")
            
            # Step 1: Navigate to quiz URL and wait for page to load
            async with self.rate_limiter:
                self.logger.debug(f"[{quiz_log_id}] Navigating to quiz URL")
                await self._optimized_page_goto(page, quiz_url)
                self.logger.debug(f"[{quiz_log_id}] Page loaded successfully")

            # Step 2: Extract quiz metadata before starting
            quiz_metadata = await self._extract_quiz_metadata(page)
            self.logger.debug(f"[{quiz_log_id}] Extracted metadata: domain={quiz_metadata.get('domain')}, topic={quiz_metadata.get('topic')}, difficulty={quiz_metadata.get('difficulty')}")
            
            # Run diagnostic if metadata looks suspicious (indicates potential issues)
            if quiz_metadata.get('domain') in ['New Player', 'Log In'] or quiz_metadata.get('topic') in ['New Player', 'Log In']:
                self.logger.warning(f"[{quiz_log_id}] Suspicious metadata detected - running diagnostic")
                await self._diagnose_quiz_page(page, quiz_url)

            # Step 3: Detect quiz type - only process compatible types
            quiz_type = await self._detect_quiz_type(page)
            self.logger.info(f"[{quiz_log_id}] Quiz type detected: {quiz_type}")
                
            if quiz_type not in ['Multiple Choice', 'Photo Quiz', 'Audio Quiz']:
                self.logger.info(f"[{quiz_log_id}] Skipping incompatible quiz type: {quiz_type}")
                return []

            # Step 4: Start the quiz if there's a start button
            await self._ensure_quiz_started(page)

            # Step 5: Play through the entire quiz, collecting questions and submitting answers
            self.logger.debug(f"[{quiz_log_id}] Starting quiz play-through process")
            questions_with_results = await self._play_through_complete_quiz(page, quiz_type)
            
            if not questions_with_results:
                self.logger.warning(f"[{quiz_log_id}] No questions extracted from quiz")
                return []

            self.logger.info(f"[{quiz_log_id}] Successfully completed quiz with {len(questions_with_results)} questions")

            # Step 6: Process questions through existing pipeline for proper formatting
            processed_questions = await self._process_extracted_questions(
                questions_with_results, {}, quiz_metadata, stats, quiz_log_id, quiz_url
            )
            
            # Step 6b: Apply parallel media downloads if enabled and questions exist
            if self.parallel_media_downloads and processed_questions:
                self.logger.debug(f"[{quiz_log_id}] Starting parallel media downloads for {len(processed_questions)} questions")
                processed_questions = await self._parallel_media_download(processed_questions, quiz_log_id)
                
            if processed_questions:
                self.logger.info(f"[{quiz_log_id}] Successfully processed {len(processed_questions)} questions")
                if stats:
                    stats['questions_extracted'] += len(processed_questions)
                
                # Step 7: INCREMENTAL SAVE - Save questions immediately after processing
                if self.incremental_save and self.csv_handler:
                    saved_count = await self._save_questions_incrementally(processed_questions, quiz_log_id)
                    if saved_count > 0:
                        self.logger.info(f"[{quiz_log_id}] 🎉 QUIZ COMPLETE: {saved_count} questions saved to CSV files!")
                    else:
                        self.logger.warning(f"[{quiz_log_id}] ⚠️ Quiz processed but no questions were saved")
            else:
                self.logger.warning(f"[{quiz_log_id}] No questions remained after processing")
                
            return processed_questions
                
        except PlaywrightTimeoutError as e:
            self.logger.error(f"[{quiz_log_id}] Timeout error: {e}")
            if stats:
                stats['quizzes_failed'] += 1
            return []
        except Exception as e:
            self.logger.error(f"[{quiz_log_id}] Unexpected error during quiz scraping: {e}")
            self.logger.debug(f"[{quiz_log_id}] Quiz scraping error details:", exc_info=True)
            if stats:
                stats['quizzes_failed'] += 1
            return []
        finally:
            try:
                await context.close()
                self.logger.debug(f"[{quiz_log_id}] Browser context closed")
            except Exception as e:
                self.logger.debug(f"[{quiz_log_id}] Error closing context: {e}")

    async def _process_extracted_questions(self, questions: List[Dict[str, Any]], descriptions: Dict[str, str], metadata: Dict[str, str], stats: Dict = None, quiz_log_id: str = "", quiz_url: str = "") -> List[Dict[str, Any]]:
        """Process and enhance extracted questions with comprehensive logging and error handling."""
        processed_questions = []
        
        self.logger.debug(f"[{quiz_log_id}] Processing {len(questions)} extracted questions")
        
        for i, question_data in enumerate(questions):
            if not question_data:
                self.logger.warning(f"[{quiz_log_id}] Skipping empty question data at index {i}")
                continue
            
            try:
                # Determine question type - prioritize audio detection
                question_text = question_data.get('question', '')
                options = question_data.get('options', [])
                
                if not question_text or len(options) < 2:
                    self.logger.warning(f"[{quiz_log_id}] Skipping invalid question {i+1}: insufficient data")
                    continue
                
                # Check if this is an audio/sound question
                if (question_data.get('isAudioQuestion') or 
                    question_data.get('isAudioQuiz') or 
                    question_data.get('audioUrl') or 
                    question_data.get('audio_path')):
                    question_type = 'sound'
                    self.logger.debug(f"[{quiz_log_id}] Question {i+1} categorized as sound due to audio elements")
                else:
                    # Use standard classification for non-audio questions
                    question_type = self.question_classifier.classify(question_text, options)
                
                question_data['type'] = question_type
                
                # Track question type statistics
                if stats and question_type in stats['questions_by_type']:
                    stats['questions_by_type'][question_type] += 1
                
                # Extract and map domain/difficulty BEFORE generating question ID
                try:
                    raw_domain = metadata.get('domain', 'Unknown')
                    raw_difficulty = metadata.get('difficulty', 'Unknown')
                    raw_topic = metadata.get('topic', 'Unknown')
                    
                    # MAPPING LOOKUP: Using centralized configuration
                    mapped_domain = self.scraper_config.map_domain(raw_domain)
                    mapped_difficulty = self.scraper_config.map_difficulty(raw_difficulty)
                    mapped_topic = self.scraper_config.map_topic(raw_topic)
                    
                    # Track mapping issues for summary reporting
                    if stats and 'mapping_issues' in stats:
                        if mapped_domain != raw_domain:
                            self.logger.debug(f"[{quiz_log_id}] Mapped domain: '{raw_domain}' -> '{mapped_domain}'")
                        else:
                            stats['mapping_issues']['domain'].add(raw_domain)
                            
                        if mapped_difficulty != raw_difficulty:
                            self.logger.debug(f"[{quiz_log_id}] Mapped difficulty: '{raw_difficulty}' -> '{mapped_difficulty}'")
                        else:
                            stats['mapping_issues']['difficulty'].add(raw_difficulty)
                            
                        if mapped_topic != raw_topic:
                            self.logger.debug(f"[{quiz_log_id}] Mapped topic: '{raw_topic}' -> '{mapped_topic}'")
                        else:
                            stats['mapping_issues']['topic'].add(raw_topic)
                    
                except Exception as mapping_error:
                    self.logger.error(f"[{quiz_log_id}] Mapping error for question {i+1}: {mapping_error}")
                    # Use fallback values
                    mapped_domain = metadata.get('domain', 'Culture')
                    mapped_difficulty = metadata.get('difficulty', 'Normal')
                    mapped_topic = metadata.get('topic', 'General')
                
                # Generate unique question ID
                question_id = self.indexer.get_next_id(question_type, mapped_domain, mapped_difficulty)
                self.logger.debug(f"[{quiz_log_id}] Generated question ID: {question_id}")
                
                # Preserve existing description/explanation or use provided descriptions
                question_number = question_data.get('questionNumber', str(i+1))
                existing_description = question_data.get('description', '')
                fallback_description = descriptions.get(question_number, '')
                description = existing_description or fallback_description
                
                # Clean and process text fields
                cleaned_question = self.text_processor.clean_question_text(question_text)
                cleaned_description = self.text_processor.clean_description_text(description)
                
                # Log explanation extraction status
                if description:
                    self.logger.debug(f"[{quiz_log_id}] Question {i+1} has explanation: {len(description)} chars")
                else:
                    self.logger.debug(f"[{quiz_log_id}] Question {i+1} missing explanation")
                
                # Handle media files based on question type
                media_filename = None
                
                try:
                    if question_type == 'sound':
                        # Handle audio file for sound questions
                        audio_url = self._extract_audio_url(question_data)
                        if audio_url:
                            if stats:
                                stats['media_downloads']['attempted'] += 1
                            
                            self.logger.debug(f"[{quiz_log_id}] Attempting audio download for question {question_id}")
                            media_filename = await self.media_handler.download_media(
                                url=audio_url,
                                question_id=question_id,
                                media_type='audio',
                                user_agent=self._get_random_user_agent()
                            )
                            
                            if media_filename:
                                if stats:
                                    stats['media_downloads']['successful'] += 1
                                self.logger.info(f"[{quiz_log_id}] Successfully downloaded audio: {media_filename}")
                            else:
                                if stats:
                                    stats['media_downloads']['failed'] += 1
                                self.logger.warning(f"[{quiz_log_id}] Failed to download audio for {question_id}")
                                
                    elif question_data.get('isPhotoQuiz') or question_data.get('imageUrl'):
                        # Handle image file for photo quiz questions
                        image_url = question_data.get('imageUrl')
                        if image_url:
                            if stats:
                                stats['media_downloads']['attempted'] += 1
                            
                            self.logger.debug(f"[{quiz_log_id}] Attempting image download for question {question_id}")
                            media_filename = await self.media_handler.download_media(
                                url=image_url,
                                question_id=question_id,
                                media_type='image',
                                user_agent=self._get_random_user_agent()
                            )
                            
                            if media_filename:
                                if stats:
                                    stats['media_downloads']['successful'] += 1
                                self.logger.info(f"[{quiz_log_id}] Successfully downloaded image: {media_filename}")
                            else:
                                if stats:
                                    stats['media_downloads']['failed'] += 1
                                self.logger.warning(f"[{quiz_log_id}] Failed to download image for {question_id}")
                
                except Exception as media_error:
                    if stats:
                        stats['media_downloads']['failed'] += 1
                    self.logger.error(f"[{quiz_log_id}] Media download error for question {question_id}: {media_error}")
                    self.logger.debug(f"[{quiz_log_id}] Media download error details:", exc_info=True)
                
                # Update question data with all metadata
                question_data.update({
                    "id": question_id,
                    "question": cleaned_question,
                    "difficulty": mapped_difficulty,
                    "domain": mapped_domain,
                    "topic": mapped_topic,
                    "correct_answer": question_data.get('correct_answer', options[0] if options else ''),
                    "description": cleaned_description,
                    "media_filename": media_filename,
                    "source_url": quiz_url
                })
                
                # Log final explanation status for debugging
                if cleaned_description:
                    self.logger.debug(f"[{quiz_log_id}] Question {question_id} final description: {len(cleaned_description)} chars")
                else:
                    self.logger.warning(f"[{quiz_log_id}] Question {question_id} has no description/explanation")
                
                processed_questions.append(question_data)
                self.logger.debug(f"[{quiz_log_id}] Successfully processed question {i+1} ({question_type}): {cleaned_question[:50]}...")
            
            except Exception as question_error:
                self.logger.error(f"[{quiz_log_id}] Error processing question {i+1}: {question_error}")
                self.logger.debug(f"[{quiz_log_id}] Question processing error details:", exc_info=True)
                # Continue with next question instead of failing entire quiz
                continue
        
        self.logger.info(f"[{quiz_log_id}] Processed {len(processed_questions)}/{len(questions)} questions successfully")
        return processed_questions

    def _log_scraping_summary(self, stats: Dict, questions: List[Dict[str, Any]]) -> None:
        """Log comprehensive scraping session summary."""
        
        self.logger.info("="*60)
        self.logger.info("SCRAPING SESSION SUMMARY")
        self.logger.info("="*60)
        
        # Overall statistics
        self.logger.info(f"Categories: {stats['categories_processed']} processed, {stats['categories_failed']} failed")
        self.logger.info(f"Quizzes: {stats['quizzes_processed']} processed, {stats['quizzes_failed']} failed")
        self.logger.info(f"Questions: {stats['questions_extracted']} extracted, {len(questions)} total")
        
        # Incremental saving info
        if self.incremental_save:
            saved_count = stats.get('questions_saved', 0)
            self.logger.info(f"💾 INCREMENTAL SAVING: {saved_count} questions saved to CSV files during scraping")
            self.logger.info(f"📁 CSV files location: {self.config['storage']['output_dir']}")
            if saved_count != len(questions):
                self.logger.warning(f"⚠️ Mismatch: {len(questions)} extracted but {saved_count} saved")
        
        # Success rates
        category_success_rate = (stats['categories_processed'] / (stats['categories_processed'] + stats['categories_failed'])) * 100 if (stats['categories_processed'] + stats['categories_failed']) > 0 else 0
        quiz_success_rate = (stats['quizzes_processed'] / (stats['quizzes_processed'] + stats['quizzes_failed'])) * 100 if (stats['quizzes_processed'] + stats['quizzes_failed']) > 0 else 0
        
        self.logger.info(f"Success rates: Categories {category_success_rate:.1f}%, Quizzes {quiz_success_rate:.1f}%")
        
        # Question type breakdown
        self.logger.info("Question types:")
        for qtype, count in stats['questions_by_type'].items():
            self.logger.info(f"  {qtype}: {count} questions")
        
        # Media download statistics
        if stats['media_downloads']['attempted'] > 0:
            media_success_rate = (stats['media_downloads']['successful'] / stats['media_downloads']['attempted']) * 100
            self.logger.info(f"Media downloads: {stats['media_downloads']['successful']}/{stats['media_downloads']['attempted']} successful ({media_success_rate:.1f}%)")
        else:
            self.logger.info("Media downloads: No media files processed")
        
        # Mapping issues
        unmapped_count = sum(len(values) for values in stats['mapping_issues'].values())
        if unmapped_count > 0:
            self.logger.warning(f"Mapping issues found: {unmapped_count} unmapped values")
            for mapping_type, values in stats['mapping_issues'].items():
                if values:
                    self.logger.warning(f"  Unmapped {mapping_type}: {list(values)}")
        else:
            self.logger.info("Mapping: All values mapped successfully")
        
        # Performance metrics
        final_indices = self.indexer.get_all_indices()
        self.logger.info("Final question indices:")
        for qtype, count in final_indices.items():
            self.logger.info(f"  {qtype}: {count}")
        
        self.logger.info("="*60)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((PlaywrightTimeoutError, Exception))
    )
    async def _get_categories(self) -> List[str]:
        """Get all category URLs from the main page with logging."""
        context = await self.browser.new_context(
            user_agent=self._get_random_user_agent()
        )
        page = await context.new_page()
        
        try:
            self.logger.debug("Fetching main categories page")
            async with self.rate_limiter:
                await self._optimized_page_goto(page, f"{self.config['scraper']['base_url']}/quizzes/")
                self.logger.debug("Categories page loaded successfully")
                
                categories = await page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a[href*="/quizzes/"]'));
                        return links.map(link => link.href);
                    }
                """)
                unique_categories = list(set(categories))  # Remove duplicates
                self.logger.info(f"Successfully discovered {len(unique_categories)} unique categories")
                return unique_categories
        except PlaywrightTimeoutError:
            self.logger.error("Timeout while loading categories page")
            raise
        except Exception as e:
            self.logger.error(f"Error getting categories: {e}")
            self.logger.debug("Categories fetch error details:", exc_info=True)
            raise
        finally:
            await context.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((PlaywrightTimeoutError, Exception))
    )
    async def _get_quiz_links(self, category_url: str) -> List[str]:
        """Get all quiz links from a category page with logging."""
        context = await self.browser.new_context(
            user_agent=self._get_random_user_agent()
        )
        page = await context.new_page()
        
        try:
            category_name = category_url.split('/')[-1][:50]  # Short identifier for logging
            self.logger.debug(f"Fetching quiz links from category: {category_name}")
            
            async with self.rate_limiter:
                await self._optimized_page_goto(page, category_url)
                self.logger.debug("Category page loaded successfully")
                
                quiz_links = await page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a[href*="/quiz/"]'));
                        return links.map(link => link.href);
                    }
                """)
                unique_quiz_links = list(set(quiz_links))  # Remove duplicates
                self.logger.debug(f"Found {len(unique_quiz_links)} unique quiz links in category {category_name}")
                return unique_quiz_links
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout while loading category page: {category_url}")
            raise
        except Exception as e:
            self.logger.error(f"Error getting quiz links for {category_url}: {e}")
            self.logger.debug("Quiz links fetch error details:", exc_info=True)
            raise
        finally:
            await context.close()

    async def _extract_quiz_metadata(self, page: Page) -> Dict[str, str]:
        """Extract metadata about the quiz with error handling."""
        try:
            metadata = {
                'difficulty': await self._get_quiz_difficulty(page),
                'domain': await self._get_quiz_domain(page),
                'topic': await self._get_quiz_topic(page)
            }
            self.logger.debug(f"Extracted quiz metadata: {metadata}")
            return metadata
        except Exception as e:
            self.logger.warning(f"Error extracting quiz metadata: {e}")
            return {
                'difficulty': 'Normal',
                'domain': 'Culture', 
                'topic': 'General'
            }

    async def _get_quiz_difficulty(self, page: Page) -> str:
        """Get the quiz difficulty level with logging."""
        try:
            difficulty = await page.evaluate("""
                () => {
                    // Try multiple strategies to find difficulty
                    const strategies = [
                        // Look in quiz metadata or description
                        () => {
                            const meta = document.querySelector('.quiz-meta, .quiz-info, .quiz-details');
                            if (meta) {
                                const text = meta.textContent.toLowerCase();
                                if (text.includes('easy') || text.includes('beginner')) return 'Easy';
                                if (text.includes('hard') || text.includes('difficult') || text.includes('expert')) return 'Hard';
                                if (text.includes('medium') || text.includes('average') || text.includes('normal')) return 'Normal';
                            }
                            return null;
                        },
                        // Look in breadcrumbs or page title
                        () => {
                            const title = document.title.toLowerCase();
                            if (title.includes('easy')) return 'Easy';
                            if (title.includes('hard') || title.includes('difficult')) return 'Hard';
                            return 'Normal';
                        }
                    ];
                    
                    for (const strategy of strategies) {
                        const result = strategy();
                        if (result) return result;
                    }
                    
                    return 'Normal'; // Default
                }
            """)
            self.logger.debug(f"Detected difficulty: {difficulty}")
            return difficulty
        except Exception as e:
            self.logger.debug(f"Error getting difficulty: {e}")
            return "Normal"

    async def _get_quiz_domain(self, page: Page) -> str:
        """
        Extract quiz domain by parsing breadcrumb navigation and mapping to internal domain list.
        
        REFACTORED BREADCRUMB-BASED DOMAIN EXTRACTION:
        ============================================
        This function implements the requested refactoring to extract domain from breadcrumbs:
        
        1. BREADCRUMB STRUCTURE: Parses navigation like "Home » Quizzes » [Entertainment Trivia] » [Comics] » Quiz"
        2. DOMAIN EXTRACTION: Takes the second-to-last breadcrumb (e.g., "Entertainment Trivia")
        3. DOMAIN MAPPING: Maps raw domain using config.py mappings (e.g., "Entertainment" → "Culture")
        4. FALLBACK HANDLING: Uses original value and logs warning if mapping not found
        5. CSV STORAGE: Saves mapped domain in the correct column via _process_extracted_questions
        
        Expected breadcrumb structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
        The [MainCategory] becomes our internal domain after mapping.
        """
        try:
            # ENHANCED BREADCRUMB EXTRACTION: Better handling of logged-out states
            breadcrumb_info = await page.evaluate("""
                () => {
                    // Strategy 1: Look for breadcrumb navigation elements with comprehensive selectors
                    const breadcrumbSelectors = [
                        '.breadcrumb a, .breadcrumbs a',
                        'nav.breadcrumb a, nav.breadcrumbs a',
                        '[itemtype*="BreadcrumbList"] a',
                        '.nav-breadcrumb a',
                        '.crumb a, .crumbs a',
                        'ol.breadcrumb a, ul.breadcrumb a',
                        '#breadcrumb a, #breadcrumbs a',
                        '.trail a, .page-trail a'
                    ];
                    
                    let breadcrumbElements = [];
                    
                    for (const selector of breadcrumbSelectors) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 2) {  // Need at least Home » Category » Subcategory
                            breadcrumbElements = Array.from(elements).map(el => ({
                                text: el.textContent.trim(),
                                href: el.href || ''
                            }));
                            break;
                        }
                    }
                    
                    // Strategy 2: Look for breadcrumb text patterns if links not found
                    if (breadcrumbElements.length === 0) {
                        const breadcrumbTextSelectors = [
                            '.breadcrumb, .breadcrumbs',
                            'nav.breadcrumb, nav.breadcrumbs', 
                            '.nav-breadcrumb',
                            '.crumb, .crumbs',
                            '#breadcrumb, #breadcrumbs',
                            '.trail, .page-trail'
                        ];
                        
                        for (const selector of breadcrumbTextSelectors) {
                            const element = document.querySelector(selector);
                            if (element) {
                                const text = element.textContent;
                                // Look for typical breadcrumb separators - FIXED: proper escaping
                                const separators = ['»', '>', '/', '\\\\', '|', '::'];
                                for (const sep of separators) {
                                    if (text.includes(sep)) {
                                        const parts = text.split(sep).map(p => p.trim()).filter(p => p);
                                        if (parts.length > 2) {
                                            breadcrumbElements = parts.map(p => ({ text: p, href: '' }));
                                            break;
                                        }
                                    }
                                }
                                if (breadcrumbElements.length > 0) break;
                            }
                        }
                    }
                    
                    // Strategy 3: Enhanced URL parsing for domain extraction 
                    const urlInfo = {
                        pathname: window.location.pathname,
                        href: window.location.href,
                        segments: window.location.pathname.split('/').filter(s => s)
                    };
                    
                    // Strategy 4: Page title analysis for domain clues
                    const titleInfo = {
                        full: document.title,
                        parts: document.title.split(/[-|–]/).map(p => p.trim())
                    };
                    
                    return {
                        breadcrumbs: breadcrumbElements,
                        url: urlInfo,
                        title: titleInfo
                    };
                }
            """)
            
            raw_domain = None
            
            # DOMAIN EXTRACTION: Get second-to-last breadcrumb as requested in the prompt
            if breadcrumb_info['breadcrumbs'] and len(breadcrumb_info['breadcrumbs']) > 2:
                # Filter out common navigation elements to get meaningful categories
                # Structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
                meaningful_breadcrumbs = [
                    b for b in breadcrumb_info['breadcrumbs'] 
                    if b['text'].lower() not in ['home', 'quizzes', 'trivia', 'quiz', 'new player', 'log in', 'register', 'login']
                ]
                
                if len(meaningful_breadcrumbs) >= 2:
                    # SECOND-TO-LAST BREADCRUMB: Extract main category as domain (as requested)
                    raw_domain = meaningful_breadcrumbs[-2]['text'].strip()
                elif len(meaningful_breadcrumbs) >= 1:
                    # Fallback to first meaningful element if only one category available
                    raw_domain = meaningful_breadcrumbs[0]['text'].strip()
            
            # ENHANCED FALLBACK 1: Smart URL path analysis
            if not raw_domain:
                url_segments = breadcrumb_info['url']['segments']
                
                # Look for category patterns in URL structure
                # Common FunTrivia patterns: /quiz/[category]/[subcategory]/quiz-name
                category_indicators = ['quiz', 'trivia']
                for i, segment in enumerate(url_segments):
                    if segment.lower() in category_indicators and i + 1 < len(url_segments):
                        next_segment = url_segments[i + 1]
                        # Clean up URL segment to readable format
                        raw_domain = next_segment.replace('-', ' ').replace('_', ' ').title()
                        # Map common URL patterns to readable names
                        domain_mappings = {
                            'Forchildren': 'For Children',
                            'Tv': 'Television',
                            'Videogames': 'Video Games',
                            'Hobbies': 'Hobbies',
                            'Celeb': 'Celebrities',
                            'Sci Tech': 'Science & Technology'
                        }
                        raw_domain = domain_mappings.get(raw_domain, raw_domain)
                        break
            
            # ENHANCED FALLBACK 2: Title-based extraction with smarter parsing
            if not raw_domain:
                title_parts = breadcrumb_info['title']['parts']
                if len(title_parts) > 1:
                    # Look for category indicators in title
                    for part in title_parts:
                        part_clean = part.strip()
                        # Skip common non-category terms
                        if part_clean.lower() not in ['funtrivia', 'quiz', 'trivia', 'test', 'questions']:
                            # Check if this part contains category-like words
                            category_words = ['entertainment', 'sports', 'history', 'science', 'movies', 'music', 'literature', 'geography', 'animals', 'people', 'world', 'for children']
                            if any(word in part_clean.lower() for word in category_words):
                                raw_domain = part_clean
                                break
                
                # If still no domain, use first meaningful title part
                if not raw_domain and title_parts:
                    raw_domain = title_parts[0].strip()
            
            # FINAL FALLBACK: Use intelligent defaults based on URL patterns
            if not raw_domain:
                url_path = breadcrumb_info['url']['pathname'].lower()
                if 'entertainment' in url_path or 'movies' in url_path or 'tv' in url_path:
                    raw_domain = "Entertainment"
                elif 'sports' in url_path:
                    raw_domain = "Sports"
                elif 'history' in url_path:
                    raw_domain = "History"
                elif 'science' in url_path:
                    raw_domain = "Science"
                elif 'children' in url_path or 'kids' in url_path:
                    raw_domain = "For Children"
                elif 'world' in url_path or 'geography' in url_path:
                    raw_domain = "World"
                elif 'people' in url_path:
                    raw_domain = "People"
                else:
                    raw_domain = "Entertainment"  # Most common category on FunTrivia
            
            self.logger.debug(f"Raw domain extracted from breadcrumbs: '{raw_domain}'")
            
            # DOMAIN MAPPING: Use centralized config.py mapping as requested in the prompt
            if raw_domain:
                mapped_domain = self.scraper_config.map_domain(raw_domain)
                self.logger.debug(f"Domain mapping: '{raw_domain}' -> '{mapped_domain}'")
                
                # LOG WARNING: If mapping not found, ScraperConfig automatically logs warning
                # and returns original value as fallback (as requested in prompt)
                
                return mapped_domain
            else:
                self.logger.warning("No domain found in breadcrumbs, using default 'Culture'")
                return "Culture"
                
        except Exception as e:
            self.logger.warning(f"Error parsing breadcrumbs for domain: {e}")
            self.logger.debug("Domain extraction error details:", exc_info=True)
            return "Culture"  # Safe fallback

    async def _get_quiz_topic(self, page: Page) -> str:
        """
        Extract quiz topic by parsing breadcrumb navigation and mapping to internal topic list.
        
        REFACTORED BREADCRUMB-BASED TOPIC EXTRACTION:
        ===========================================
        This function implements the requested refactoring to extract topic from breadcrumbs:
        
        1. BREADCRUMB STRUCTURE: Parses navigation like "Home » Quizzes » [Entertainment Trivia] » [Comics] » Quiz"
        2. TOPIC EXTRACTION: Takes the last breadcrumb (e.g., "Comics")
        3. TOPIC MAPPING: Maps raw topic using config.py mappings (e.g., "Comics" → "Entertainment")
        4. FALLBACK HANDLING: Uses original value and logs warning if mapping not found
        5. CSV STORAGE: Saves mapped topic in the correct column via _process_extracted_questions
        
        Expected breadcrumb structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
        The [SubCategory] becomes our internal topic after mapping.
        """
        try:
            # ENHANCED BREADCRUMB EXTRACTION: Better handling of logged-out states
            breadcrumb_info = await page.evaluate("""
                () => {
                    // Strategy 1: Look for breadcrumb navigation elements with comprehensive selectors
                    const breadcrumbSelectors = [
                        '.breadcrumb a, .breadcrumbs a',
                        'nav.breadcrumb a, nav.breadcrumbs a',
                        '[itemtype*="BreadcrumbList"] a',
                        '.nav-breadcrumb a',
                        '.crumb a, .crumbs a',
                        'ol.breadcrumb a, ul.breadcrumb a',
                        '#breadcrumb a, #breadcrumbs a',
                        '.trail a, .page-trail a'
                    ];
                    
                    let breadcrumbElements = [];
                    
                    for (const selector of breadcrumbSelectors) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 2) {  // Need at least Home » Category » Subcategory
                            breadcrumbElements = Array.from(elements).map(el => ({
                                text: el.textContent.trim(),
                                href: el.href || ''
                            }));
                            break;
                        }
                    }
                    
                    // Strategy 2: Look for breadcrumb text patterns if links not found
                    if (breadcrumbElements.length === 0) {
                        const breadcrumbTextSelectors = [
                            '.breadcrumb, .breadcrumbs',
                            'nav.breadcrumb, nav.breadcrumbs', 
                            '.nav-breadcrumb',
                            '.crumb, .crumbs',
                            '#breadcrumb, #breadcrumbs',
                            '.trail, .page-trail'
                        ];
                        
                        for (const selector of breadcrumbTextSelectors) {
                            const element = document.querySelector(selector);
                            if (element) {
                                const text = element.textContent;
                                // Look for typical breadcrumb separators - FIXED: proper escaping
                                const separators = ['»', '>', '/', '\\\\', '|', '::'];
                                for (const sep of separators) {
                                    if (text.includes(sep)) {
                                        const parts = text.split(sep).map(p => p.trim()).filter(p => p);
                                        if (parts.length > 2) {
                                            breadcrumbElements = parts.map(p => ({ text: p, href: '' }));
                                            break;
                                        }
                                    }
                                }
                                if (breadcrumbElements.length > 0) break;
                            }
                        }
                    }
                    
                    // Strategy 3: Enhanced URL parsing for topic extraction 
                    const urlInfo = {
                        pathname: window.location.pathname,
                        href: window.location.href,
                        segments: window.location.pathname.split('/').filter(s => s),
                        filename: window.location.pathname.split('/').pop().replace('.html', '')
                    };
                    
                    // Strategy 4: Page title analysis for topic clues
                    const titleInfo = {
                        full: document.title,
                        parts: document.title.split(/[-|–]/).map(p => p.trim())
                    };
                    
                    return {
                        breadcrumbs: breadcrumbElements,
                        url: urlInfo,
                        title: titleInfo
                    };
                }
            """)
            
            raw_topic = None
            
            # TOPIC EXTRACTION: Get last meaningful breadcrumb as requested in the prompt
            if breadcrumb_info['breadcrumbs'] and len(breadcrumb_info['breadcrumbs']) > 1:
                # Filter out common navigation elements to get meaningful categories
                # Structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
                meaningful_breadcrumbs = [
                    b for b in breadcrumb_info['breadcrumbs'] 
                    if b['text'].lower() not in ['home', 'quizzes', 'trivia', 'quiz', 'new player', 'log in', 'register', 'login']
                ]
                
                if len(meaningful_breadcrumbs) >= 1:
                    # LAST BREADCRUMB: Extract subcategory as topic (as requested)
                    raw_topic = meaningful_breadcrumbs[-1]['text'].strip()
            
            # ENHANCED FALLBACK 1: Smart URL path analysis for topic
            if not raw_topic:
                url_segments = breadcrumb_info['url']['segments']
                
                # Look for subcategory patterns in URL structure
                # Common FunTrivia patterns: /quiz/[category]/[subcategory]/quiz-name
                if len(url_segments) >= 3:
                    # Take the segment before the quiz filename as topic
                    topic_segment = url_segments[-2] if len(url_segments) > 2 else url_segments[-1]
                    # Clean up URL segment to readable format
                    raw_topic = topic_segment.replace('-', ' ').replace('_', ' ').title()
                    
                    # Map common URL patterns to readable names
                    topic_mappings = {
                        'Movies A-C': 'Movies',
                        'Movies D-G': 'Movies', 
                        'Our World For Kids': 'Geography',
                        'College Sports': 'Sports',
                        'Dog Training': 'Animals',
                        'Nascar By Season': 'Sports'
                    }
                    raw_topic = topic_mappings.get(raw_topic, raw_topic)
                
                # Alternative: extract from quiz filename
                if not raw_topic:
                    filename = breadcrumb_info['url']['filename']
                    if filename and filename != 'index':
                        # Extract meaningful words from filename
                        words = filename.replace('-', ' ').replace('_', ' ').split()
                        if len(words) >= 2:
                            # Take first few meaningful words as topic
                            topic_words = [w.title() for w in words[:3] if w.lower() not in ['quiz', 'trivia', 'test']]
                            if topic_words:
                                raw_topic = ' '.join(topic_words)
            
            # ENHANCED FALLBACK 2: Title-based extraction with smarter parsing
            if not raw_topic:
                title_parts = breadcrumb_info['title']['parts']
                if len(title_parts) > 1:
                    # Look for topic indicators in title
                    for part in title_parts:
                        part_clean = part.strip()
                        # Skip common non-topic terms and site name
                        if part_clean.lower() not in ['funtrivia', 'quiz', 'trivia', 'test', 'questions']:
                            # Check if this part seems specific enough to be a topic
                            if len(part_clean.split()) >= 1 and len(part_clean) > 3:
                                raw_topic = part_clean
                                break
                
                # If still no topic, use first meaningful title part
                if not raw_topic and title_parts:
                    first_part = title_parts[0].strip()
                    if first_part.lower() != 'funtrivia':
                        raw_topic = first_part
            
            # FINAL FALLBACK: Use intelligent defaults based on domain context
            if not raw_topic:
                url_path = breadcrumb_info['url']['pathname'].lower()
                # Try to infer topic from URL context
                if 'movies' in url_path:
                    raw_topic = "Movies"
                elif 'tv' in url_path or 'television' in url_path:
                    raw_topic = "Television"
                elif 'music' in url_path:
                    raw_topic = "Music"
                elif 'sports' in url_path:
                    raw_topic = "General Sports"
                elif 'history' in url_path:
                    raw_topic = "General History"
                elif 'science' in url_path:
                    raw_topic = "General Science"
                elif 'animals' in url_path:
                    raw_topic = "Animals"
                elif 'children' in url_path or 'kids' in url_path:
                    raw_topic = "For Children"
                elif 'world' in url_path or 'geography' in url_path:
                    raw_topic = "Geography"
                elif 'people' in url_path:
                    raw_topic = "General People"
                else:
                    raw_topic = "General"  # Generic fallback
            
            self.logger.debug(f"Raw topic extracted from breadcrumbs: '{raw_topic}'")
            
            # TOPIC MAPPING: Use centralized config.py mapping as requested in the prompt
            if raw_topic:
                mapped_topic = self.scraper_config.map_topic(raw_topic)
                self.logger.debug(f"Topic mapping: '{raw_topic}' -> '{mapped_topic}'")
                
                # LOG WARNING: If mapping not found, ScraperConfig automatically logs warning
                # and returns original value as fallback (as requested in prompt)
                
                return mapped_topic
            else:
                self.logger.warning("No topic found in breadcrumbs, using default 'General'")
                return "General"
                
        except Exception as e:
            self.logger.warning(f"Error parsing breadcrumbs for topic: {e}")
            self.logger.debug("Topic extraction error details:", exc_info=True)
            return "General"  # Safe fallback

    async def _detect_quiz_type(self, page: Page) -> str:
        """Detect the type of quiz from the page content with logging."""
        try:
            quiz_type = await page.evaluate("""
                () => {
                    // Strategy 1: Look for quiz type in page text/headings
                    const pageText = document.body.innerText.toLowerCase();
                    
                    // Check for explicit quiz type mentions (prioritize audio/sound detection)
                    if (pageText.includes('audio quiz') || pageText.includes('sound quiz') || 
                        pageText.includes('listen to') || pageText.includes('hearing quiz')) return 'Audio Quiz';
                    if (pageText.includes('photo quiz')) return 'Photo Quiz';
                    if (pageText.includes('match quiz')) return 'Match Quiz';
                    if (pageText.includes('ordering quiz')) return 'Ordering Quiz';
                    if (pageText.includes('label quiz')) return 'Label Quiz';
                    if (pageText.includes('classification quiz')) return 'Classification Quiz';
                    if (pageText.includes('multiple choice')) return 'Multiple Choice';
                    
                    // Strategy 2: Look for audio elements (highest priority for sound detection)
                    const audioElements = document.querySelectorAll('audio, embed[type*="audio"], object[type*="audio"]');
                    if (audioElements.length > 0) {
                        return 'Audio Quiz';
                    }
                    
                    // Strategy 3: Look for audio file links or sound-related buttons
                    const audioLinks = document.querySelectorAll('a[href*=".mp3"], a[href*=".wav"], a[href*=".ogg"], a[href*=".m4a"]');
                    const soundButtons = document.querySelectorAll('button[onclick*="play"], button[onclick*="sound"], .play-button, .sound-button');
                    if (audioLinks.length > 0 || soundButtons.length > 0) {
                        return 'Audio Quiz';
                    }
                    
                    // Strategy 4: Look for embedded audio players (Flash, HTML5, etc.)
                    const audioPlayers = document.querySelectorAll('embed[src*=".mp3"], embed[src*=".wav"], object[data*=".mp3"], object[data*=".wav"]');
                    if (audioPlayers.length > 0) {
                        return 'Audio Quiz';
                    }
                    
                    // Strategy 5: Look for sound-related text patterns in questions
                    const questionTexts = document.querySelectorAll('b, strong, .question');
                    for (const qEl of questionTexts) {
                        const text = qEl.textContent.toLowerCase();
                        if (text.includes('listen to') || text.includes('what sound') || 
                            text.includes('hear the') || text.includes('audio clip') ||
                            text.includes('play the') || text.includes('sound of') ||
                            text.includes('tune') || text.includes('melody')) {
                            return 'Audio Quiz';
                        }
                    }
                    
                    // Strategy 6: Look for images in question areas (indicates Photo Quiz)
                    const questionImages = document.querySelectorAll('img');
                    let questionAreaImages = 0;
                    
                    questionImages.forEach(img => {
                        const src = img.src || '';
                        const alt = img.alt || '';
                        // Filter out UI images, look for content images
                        if (!src.includes('icon') && !src.includes('button') && 
                            !src.includes('logo') && !alt.includes('icon') &&
                            img.width > 50 && img.height > 50) {
                            questionAreaImages++;
                        }
                    });
                    
                    if (questionAreaImages > 0) return 'Photo Quiz';
                    
                    // Strategy 7: Look for specific UI patterns
                    // Match quiz has drag/drop or connection elements
                    if (document.querySelector('.match-item, .drag-item, .drop-zone')) {
                        return 'Match Quiz';
                    }
                    
                    // Ordering quiz has sortable lists
                    if (document.querySelector('.sortable, .order-item, [draggable="true"]')) {
                        return 'Ordering Quiz';
                    }
                    
                    // Label quiz has clickable areas on images
                    if (document.querySelector('.label-point, .clickable-area, map area')) {
                        return 'Label Quiz';
                    }
                    
                    // Strategy 8: Default to Multiple Choice if we find radio buttons
                    const radioInputs = document.querySelectorAll('input[type="radio"]');
                    if (radioInputs.length > 0) {
                        return 'Multiple Choice';
                    }
                    
                    // Strategy 9: Look at URL patterns
                    const url = window.location.href;
                    if (url.includes('audio') || url.includes('sound') || url.includes('music')) return 'Audio Quiz';
                    if (url.includes('photo')) return 'Photo Quiz';
                    if (url.includes('match')) return 'Match Quiz';
                    if (url.includes('order')) return 'Ordering Quiz';
                    
                    return 'Multiple Choice'; // Default fallback
                }
            """)
            
            self.logger.debug(f"Detected quiz type: {quiz_type}")
            return quiz_type
            
        except Exception as e:
            self.logger.debug(f"Error detecting quiz type: {e}")
            return "Multiple Choice"  # Default fallback

    async def _ensure_quiz_started(self, page: Page) -> None:
        """
        Ensure the quiz is started by clicking the start button if present.
        This handles various FunTrivia quiz start interfaces.
        """
        try:
            # Look for various start button patterns
            start_selectors = [
                'input[type="submit"][value*="Start"]',
                'input[value*="Take Quiz"]', 
                'button:has-text("Start")',
                'button:has-text("Begin")',
                'input[value*="Begin"]',
                '.start-button',
                'a[href*="start"]'
            ]
            
            start_btn = None
            for selector in start_selectors:
                try:
                    start_btn = await page.query_selector(selector)
                    if start_btn and await start_btn.is_visible() and await start_btn.is_enabled():
                        self.logger.debug(f"Found start button with selector: {selector}")
                        break
                    else:
                        start_btn = None
                except Exception:
                    continue
            
            if start_btn:
                await start_btn.click()
                self.logger.info("Clicked Start Quiz button - waiting for quiz to load")
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['quiz_wait'])
            else:
                self.logger.info("No start button found - quiz may already be started")
                
        except Exception as e:
            self.logger.warning(f"Error with quiz start process: {e}")

    async def _play_through_complete_quiz(self, page: Page, quiz_type: str) -> List[Dict[str, Any]]:
        """
        Play through the entire quiz from start to finish, ensuring we reach the results page.
        
        This method handles:
        - Single-page quizzes (all questions on one page)
        - Multi-page quizzes (questions spread across pages)
        - Step-by-step quizzes (one question per page)
        
        Returns questions with correct answers and explanations extracted from results page.
        """
        all_questions = []
        
        try:
            # Step 1: Extract questions from current page(s)
            if quiz_type == 'Photo Quiz':
                questions = await self._extract_photo_quiz_questions(page)
            elif quiz_type == 'Audio Quiz':
                questions = await self._extract_audio_quiz_questions(page)
            else:
                questions = await self._extract_questions_robust(page)
            
            if not questions:
                self.logger.warning("No questions found on quiz page")
                return []
            
            all_questions.extend(questions)
            self.logger.info(f"Extracted {len(questions)} questions from quiz page(s)")

            # Step 2: Submit answers for all questions (always select first option)
            if self.fast_radio_button_selection:
                selected_count = await self._fast_radio_button_interaction(page, questions)
                self.logger.info(f"Fast radio selection: {selected_count}/{len(questions)} questions selected")
            else:
                await self._submit_all_quiz_answers(page, questions)
                self.logger.info(f"Standard radio selection completed for {len(questions)} questions")
            
            # Add a short wait after radio selection to ensure form is ready
            await asyncio.sleep(1)
            
            # Step 3: Submit the quiz and navigate to results page
            results_reached = await self._submit_quiz_to_results(page)
            
            if not results_reached:
                self.logger.warning("Failed to reach results page - returning questions without enhanced data")
                return questions
            
            # Step 4: Extract correct answers and explanations from results page
            questions_with_results = await self._extract_complete_results(page, all_questions)
            
            return questions_with_results
            
        except Exception as e:
            self.logger.error(f"Error playing through quiz: {e}")
            return all_questions

    async def _submit_all_quiz_answers(self, page: Page, questions: List[Dict[str, Any]]) -> None:
        """
        Submit answers for all questions in the quiz.
        Always selects the first available option for each question.
        
        ENHANCED ANSWER SELECTION:
        ========================
        This function handles multiple quiz layouts and radio button patterns
        found across different FunTrivia quiz types, with improved error handling.
        """
        selected_count = 0
        
        try:
            # Strategy 1: Try to find all radio buttons first to verify quiz format
            all_radios = await page.query_selector_all('input[type="radio"]')
            self.logger.debug(f"Found {len(all_radios)} total radio buttons on page")
            
            if len(all_radios) == 0:
                self.logger.warning("No radio buttons found on page - may be a different quiz format")
                # Try alternative selectors for different quiz types
                alternative_selectors = [
                    'input[type="checkbox"]',  # Some quizzes use checkboxes
                    'button[data-answer]',     # Interactive button-based quizzes
                    '.answer-option input',    # CSS class-based options
                    'form input[name*="q"]'    # Form-based inputs
                ]
                
                for selector in alternative_selectors:
                    alt_inputs = await page.query_selector_all(selector)
                    if len(alt_inputs) > 0:
                        self.logger.info(f"Found {len(alt_inputs)} alternative input elements with selector: {selector}")
                        # If we find alternative inputs, we'll try to work with them
                        all_radios = alt_inputs
                        break
            
            if len(all_radios) == 0:
                raise Exception("No selectable elements found - cannot submit quiz")
            
            # Strategy 1.5: For Photo Quiz types, try to make radio buttons visible
            if len(all_radios) > 0:
                visible_count = 0
                for radio in all_radios[:5]:  # Check first few
                    try:
                        is_visible = await radio.is_visible()
                        if is_visible:
                            visible_count += 1
                    except:
                        pass
                
                if visible_count == 0:
                    self.logger.warning("All radio buttons are hidden - attempting to make them visible")
                    await self._make_radio_buttons_visible(page)
            
            # Strategy 2: Iterate through questions and find matching radio buttons
            for i, question in enumerate(questions):
                question_num = question.get('questionNumber', str(i+1))
                
                # Comprehensive naming patterns for radio buttons
                name_patterns = [
                    f'q{question_num}',
                    f'question{question_num}', 
                    f'q{i+1}',
                    f'question{i+1}',
                    f'answer{question_num}',
                    f'ans{question_num}',
                    f'a{question_num}',
                    f'opt{question_num}',
                    f'choice{question_num}'
                ]
                
                answer_selected = False
                
                # Try each naming pattern
                for name_pattern in name_patterns:
                    try:
                        # Look for radio buttons with this name pattern
                        radios = await page.query_selector_all(f'input[name="{name_pattern}"][type="radio"]')
                        
                        # If no radios found, try alternative input types
                        if len(radios) == 0:
                            radios = await page.query_selector_all(f'input[name="{name_pattern}"]')
                        
                        if radios and len(radios) > 0:
                            # Wait for element to be ready and select first option
                            first_radio = radios[0]
                            
                            # Enhanced visibility and interaction handling
                            success = await self._interact_with_radio_button(first_radio, question_num, name_pattern)
                            
                            if success:
                                selected_count += 1
                                answer_selected = True
                                self.logger.debug(f"Selected first option for question {question_num} (pattern: {name_pattern})")
                                break
                        
                    except Exception as e:
                        self.logger.debug(f"Failed to select answer with pattern {name_pattern}: {e}")
                        continue
                
                # Strategy 3: If no named radio found, try positional selection
                if not answer_selected:
                    try:
                        # Try scrolling to the question area first
                        await page.evaluate(f"""
                            () => {{
                                const questionElements = document.querySelectorAll('b, strong, .question');
                                if (questionElements[{i}]) {{
                                    questionElements[{i}].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                }}
                            }}
                        """)
                        await page.wait_for_timeout(500)  # Allow scroll to complete
                        
                        # Find radio buttons in the vicinity of this question
                        question_radios = await page.query_selector_all('input[type="radio"]')
                        if question_radios and len(question_radios) > 0:
                            # Calculate which radio buttons belong to this question
                            radios_per_question = len(question_radios) // len(questions)
                            if radios_per_question > 0:
                                start_index = i * radios_per_question
                                if start_index < len(question_radios):
                                    target_radio = question_radios[start_index]
                                    success = await self._interact_with_radio_button(target_radio, question_num, "positional")
                                    if success:
                                        selected_count += 1
                                        answer_selected = True
                                        self.logger.debug(f"Selected answer for question {question_num} using positional selection")
                    
                    except Exception as e:
                        self.logger.debug(f"Positional selection failed for question {question_num}: {e}")
                
                if not answer_selected:
                    self.logger.warning(f"Could not select answer for question {question_num}")
            
            self.logger.info(f"Successfully selected answers for {selected_count}/{len(questions)} questions")
            
            # More lenient threshold - allow submission if we selected at least some answers
            if selected_count == 0:
                raise Exception("No radio buttons found - cannot submit quiz")
            elif selected_count < len(questions) * 0.5:  # Less than 50% success
                self.logger.warning(f"Only selected {selected_count}/{len(questions)} answers - may affect results quality")
                
        except Exception as e:
            self.logger.error(f"Error submitting quiz answers: {e}")
            raise

    async def _make_radio_buttons_visible(self, page: Page) -> None:
        """
        Attempt to make hidden radio buttons visible through various interactions.
        
        RADIO BUTTON VISIBILITY ENHANCEMENT:
        ===================================
        This function tries multiple strategies to reveal hidden radio buttons
        that are present in the DOM but not visible due to CSS/JavaScript.
        """
        try:
            self.logger.debug("Attempting to make radio buttons visible...")
            
            # Strategy 1: Scroll through the page to trigger visibility
            await page.evaluate("""
                () => {
                    // Scroll to top first
                    window.scrollTo(0, 0);
                    
                    // Then scroll through the page gradually
                    const height = document.body.scrollHeight;
                    const steps = 5;
                    const stepSize = height / steps;
                    
                    for (let i = 0; i <= steps; i++) {
                        setTimeout(() => {
                            window.scrollTo(0, i * stepSize);
                        }, i * 100);
                    }
                }
            """)
            await page.wait_for_timeout(1000)
            
            # Strategy 2: Click on question containers to trigger interaction
            await page.evaluate("""
                () => {
                    const questionElements = document.querySelectorAll('b, strong, .question, h3, h4');
                    questionElements.forEach((el, index) => {
                        if (index < 3) {  // Only click first few to avoid overwhelming
                            try {
                                el.click();
                                el.focus();
                            } catch (e) {}
                        }
                    });
                }
            """)
            await page.wait_for_timeout(500)
            
            # Strategy 3: Try to remove hidden CSS properties
            await page.evaluate("""
                () => {
                    const radios = document.querySelectorAll('input[type="radio"]');
                    radios.forEach(radio => {
                        try {
                            // Remove common hiding styles
                            radio.style.display = 'inline';
                            radio.style.visibility = 'visible';
                            radio.style.opacity = '1';
                            
                            // Also try to make parent containers visible
                            let parent = radio.parentElement;
                            let depth = 0;
                            while (parent && depth < 3) {
                                parent.style.display = 'block';
                                parent.style.visibility = 'visible';
                                parent.style.opacity = '1';
                                parent = parent.parentElement;
                                depth++;
                            }
                        } catch (e) {}
                    });
                }
            """)
            await page.wait_for_timeout(500)
            
            # Strategy 4: Trigger common events that might reveal elements
            await page.evaluate("""
                () => {
                    // Trigger resize event
                    window.dispatchEvent(new Event('resize'));
                    
                    // Trigger load event
                    window.dispatchEvent(new Event('load'));
                    
                    // Focus on document
                    document.body.focus();
                    
                    // Try clicking on the page body
                    document.body.click();
                }
            """)
            await page.wait_for_timeout(500)
            
            self.logger.debug("Visibility enhancement attempts completed")
            
        except Exception as e:
            self.logger.debug(f"Error during visibility enhancement: {e}")

    async def _interact_with_radio_button(self, radio_element, question_num: str, pattern: str) -> bool:
        """
        Enhanced radio button interaction with multiple fallback methods.
        
        ROBUST RADIO BUTTON INTERACTION:
        ==============================
        This function tries multiple methods to interact with radio buttons,
        including handling visibility issues and using JavaScript fallbacks.
        """
        try:
            # Method 1: Check current visibility and try standard interaction
            await radio_element.wait_for_element_state('stable', timeout=3000)
            
            is_visible = await radio_element.is_visible()
            is_enabled = await radio_element.is_enabled()
            
            if is_visible and is_enabled:
                try:
                    await radio_element.click(timeout=5000)
                    return True
                except Exception:
                    pass
        
            # Method 2: Try to scroll the element into view and make it visible
            if not is_visible:
                self.logger.debug(f"Radio button not visible for pattern {pattern} - attempting to make visible")
                
                try:
                    # Scroll element into view
                    await radio_element.scroll_into_view_if_needed()
                    await asyncio.sleep(0.3)
                    
                    # Try to remove hiding styles
                    await radio_element.evaluate("""
                        element => {
                            element.style.display = 'inline';
                            element.style.visibility = 'visible';
                            element.style.opacity = '1';
                            element.style.position = 'static';
                            
                            // Also modify parent containers
                            let parent = element.parentElement;
                            let depth = 0;
                            while (parent && depth < 2) {
                                parent.style.display = 'block';
                                parent.style.visibility = 'visible';
                                parent.style.opacity = '1';
                                parent = parent.parentElement;
                                depth++;
                            }
                        }
                    """)
                    await asyncio.sleep(0.2)
                    
                    # Try clicking again
                    if await radio_element.is_visible():
                        await radio_element.click(timeout=3000)
                        return True
                        
                except Exception as e:
                    self.logger.debug(f"Failed to make radio button visible: {e}")
            
            # Method 3: JavaScript force-click (last resort)
            try:
                await radio_element.evaluate('element => element.click()')
                # Verify it was actually selected
                is_checked = await radio_element.is_checked()
                if is_checked:
                    return True
            except Exception as e:
                self.logger.debug(f"JavaScript click failed: {e}")
            
            # Method 4: Dispatch events manually
            try:
                await radio_element.evaluate("""
                    element => {
                        element.checked = true;
                        element.dispatchEvent(new Event('change', { bubbles: true }));
                        element.dispatchEvent(new Event('click', { bubbles: true }));
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                """)
                
                is_checked = await radio_element.is_checked()
                if is_checked:
                    return True
            except Exception as e:
                self.logger.debug(f"Event dispatch failed: {e}")
            
            self.logger.debug(f"Radio button not interactable for pattern {pattern} (visible: {is_visible}, enabled: {is_enabled})")
            return False
            
        except Exception as e:
            self.logger.debug(f"Radio button interaction failed for pattern {pattern}: {e}")
            return False

    async def _submit_quiz_to_results(self, page: Page) -> bool:
        """
        Submit the completed quiz and navigate to the results page.
        Returns True if successfully reached results page, False otherwise.
        """
        try:
            # Look for submit/finish buttons with comprehensive selectors
            submit_selectors = [
                'input[type="submit"][value*="Score"]',
                'input[type="submit"][value*="Submit"]', 
                'input[type="submit"][value*="Finish"]',
                'input[type="submit"][value*="Complete"]',
                'button[type="submit"]',
                'input[value*="Finish"]',
                'input[value*="Score"]',
                'button:has-text("Submit")',
                'button:has-text("Finish")',
                'button:has-text("Complete")',
                'button:has-text("Score")',
                '.submit-button',
                '.finish-button',
                'form input[type="submit"]'
            ]
            
            submit_btn = None
            for selector in submit_selectors:
                try:
                    submit_btn = await page.query_selector(selector)
                    if submit_btn:
                        is_visible = await submit_btn.is_visible()
                        is_enabled = await submit_btn.is_enabled()
                        if is_visible and is_enabled:
                            self.logger.debug(f"Found submit button with selector: {selector}")
                            break
                        else:
                            submit_btn = None
                except Exception:
                    continue
            
            if not submit_btn:
                self.logger.error("No submit button found - cannot complete quiz")
                return False
            
            # Submit the quiz
            await submit_btn.click()
            self.logger.info("Submitted quiz - waiting for results page")
            
            # Wait for results page with multiple strategies
            results_loaded = await self._wait_for_results_page(page)
            
            if results_loaded:
                self.logger.info("Successfully reached results page")
                return True
            else:
                self.logger.warning("Results page did not load properly")
                return False
                
        except Exception as e:
            self.logger.error(f"Error submitting quiz to results: {e}")
            return False

    async def _wait_for_results_page(self, page: Page) -> bool:
        """
        Wait for the results page to load using multiple strategies.
        Returns True if results page is loaded, False otherwise.
        
        SPEED OPTIMIZATION AWARE:
        For explanation extraction to work properly, we always need to wait
        for the results page to fully load, regardless of speed profile.
        """
        try:
            # Strategy 1: Wait for network idle (most reliable) - ALWAYS for results page
            # This is critical for description extraction regardless of speed profile
            try:
                if self.speed_profile in ['aggressive', 'turbo']:
                    # Even fast profiles need proper results page loading for descriptions
                    await page.wait_for_load_state('networkidle', timeout=45000)
                    self.logger.debug("Results page loaded - network idle detected (fast profile)")
                else:
                    await page.wait_for_load_state('networkidle', timeout=60000)
                    self.logger.debug("Results page loaded - network idle detected")
            except Exception:
                self.logger.debug("Network idle timeout - trying alternative detection")
                # For fast profiles, add extra wait time to ensure content loads
                if self.speed_profile in ['fast', 'aggressive', 'turbo']:
                    self.logger.debug("Adding extra wait for results page content (fast profile)")
                    await asyncio.sleep(3)
            
            # Strategy 2: Wait for specific result page elements
            result_indicators = [
                '.results', '.quiz-results', '.score', '.explanation',
                '.questionReview', '.questionTable', '.result-item',
                '.question-result', '.correct-answer', '.quiz-score'
            ]
            
            for indicator in result_indicators:
                try:
                    await page.wait_for_selector(indicator, timeout=30000)
                    self.logger.debug(f"Results page detected by element: {indicator}")
                    return True
                except Exception:
                    continue
            
            # Strategy 3: Check URL for results indicators
            try:
                current_url = page.url
                if any(keyword in current_url.lower() for keyword in ['score', 'result', 'finish', 'complete']):
                    self.logger.debug("Results page detected by URL pattern")
                    return True
            except Exception:
                pass
            
            # Strategy 4: Check page content for results indicators
            try:
                page_text = await page.evaluate('document.body.innerText.toLowerCase()')
                if any(keyword in page_text for keyword in ['your score', 'results', 'correct answer', 'explanation']):
                    self.logger.debug("Results page detected by content analysis")
                    return True
            except Exception:
                pass
            
            # If all else fails, wait a moment and proceed
            await asyncio.sleep(3)
            self.logger.warning("Results page detection uncertain - proceeding with available content")
            return True
            
        except Exception as e:
            self.logger.error(f"Error waiting for results page: {e}")
            return False

    async def _extract_complete_results(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Comprehensive extraction of correct answers and explanations from the results page.
        
        RESULTS PAGE EXPLANATION EXTRACTION COORDINATOR:
        ==============================================
        This function coordinates the extraction of explanations/descriptions from the quiz results page.
        It implements multiple fallback strategies to ensure maximum explanation extraction success.
        
        EXTRACTION STRATEGY HIERARCHY:
        1. **Structured Result Blocks** (`_extract_from_result_blocks`)
           - Primary method: Parses individual result blocks for each question
           - Handles "Interesting Information" sections and multi-paragraph explanations
           - Works with most FunTrivia quiz result layouts
        
        2. **Text-Based Parsing** (`_extract_from_text_results`) 
           - Fallback method: Parses raw page text when structured parsing fails
           - Useful for alternative layouts or when CSS selectors don't match
           - Extracts explanations based on text patterns and question numbers
        
        3. **Basic Enhancement** (`_enhance_questions_basic`)
           - Last resort: Provides basic question data with empty explanation fields
           - Ensures scraping continues even if explanation extraction completely fails
           - Logs warnings about missing explanations
        
        EXPLANATION INTEGRATION:
        - Extracted explanations are stored in both "Hint" and "Description" CSV columns
        - Text is cleaned and normalized for proper CSV storage
        - Missing explanations result in blank fields and logged warnings
        - Process is non-blocking: quiz data is preserved even if explanations fail
        """
        try:
            self.logger.info("Starting comprehensive results extraction from results page")
            
            # Add extra wait for fast profiles to ensure explanations are loaded
            if self.speed_profile in ['fast', 'aggressive', 'turbo']:
                self.logger.debug("Adding extra wait for description extraction (fast profile)")
                await asyncio.sleep(2)
            
            # Strategy 1: Try full page text extraction (primary method)
            self.logger.info("Attempting Strategy 1: Full page text extraction")
            enhanced_questions = await self._extract_from_full_page_text(page, original_questions)
            if enhanced_questions and len(enhanced_questions) == len(original_questions):
                # Check if we actually got both descriptions AND correct answers
                descriptions_found = sum(1 for q in enhanced_questions if q.get('description'))
                correct_answers_found = sum(1 for q in enhanced_questions if q.get('correct_answer'))
                
                self.logger.info(f"Strategy 1 results: {descriptions_found}/{len(enhanced_questions)} descriptions, {correct_answers_found}/{len(enhanced_questions)} correct answers")
                
                # Accept if we got either good descriptions or correct answers (or both)
                if descriptions_found > 0 or correct_answers_found > len(enhanced_questions) * 0.5:
                    self.logger.info("Strategy 1 successful - using full page text extraction results")
                    # Ensure correct answers are properly matched with options to prevent CSV formatting issues
                    for question in enhanced_questions:
                        if question.get('correct_answer') and question.get('options'):
                            answer = question['correct_answer']
                            options = question['options']
                            # If answer doesn't exactly match any option, try to find best match
                            if answer not in options:
                                for opt in options:
                                    if (opt.lower().strip() == answer.lower().strip() or
                                        opt.lower().strip() in answer.lower().strip() or
                                        answer.lower().strip() in opt.lower().strip()):
                                        question['correct_answer'] = opt  # Use exact option text
                                        self.logger.debug(f"Corrected answer match: '{answer}' -> '{opt}'")
                                        break
                    return enhanced_questions
            
            # Strategy 2: Look for structured result blocks (fallback)
            self.logger.warning("Strategy 1 failed - trying Strategy 2: Structured result blocks")
            enhanced_questions = await self._extract_from_result_blocks(page, original_questions)
            if enhanced_questions and len(enhanced_questions) == len(original_questions):
                descriptions_found = sum(1 for q in enhanced_questions if q.get('description'))
                correct_answers_found = sum(1 for q in enhanced_questions if q.get('correct_answer'))
                
                self.logger.info(f"Strategy 2 results: {descriptions_found}/{len(enhanced_questions)} descriptions, {correct_answers_found}/{len(enhanced_questions)} correct answers")
                
                if descriptions_found > 0 or correct_answers_found > 0:
                    self.logger.info("Strategy 2 successful - using structured result blocks")
                    return enhanced_questions
            
            # Strategy 3: Parse results from text-based format (fallback)
            self.logger.warning("Strategy 2 failed - trying Strategy 3: Text-based extraction")
            enhanced_questions = await self._extract_from_text_results(page, original_questions)
            if enhanced_questions:
                descriptions_found = sum(1 for q in enhanced_questions if q.get('description'))
                self.logger.info(f"Strategy 3 results: {descriptions_found}/{len(enhanced_questions)} descriptions")
                if descriptions_found > 0:
                    self.logger.info("Strategy 3 successful - using text-based extraction")
                    return enhanced_questions
            
            # Strategy 4: Last resort - use original questions with minimal enhancement
            self.logger.warning("All extraction strategies failed - using basic enhancement (Strategy 4)")
            return await self._enhance_questions_basic(original_questions)
            
        except Exception as e:
            self.logger.error(f"Error in comprehensive results extraction: {e}")
            return await self._enhance_questions_basic(original_questions)

    async def _extract_from_full_page_text(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract descriptions from the full page text content.
        
        This method gets the entire page text and uses regex patterns to extract
        descriptions that appear after "The correct answer was..." for each question.
        """
        try:
            self.logger.info("Attempting full page text extraction for descriptions")
            
            # Get the full page text content
            page_text = await page.inner_text("body")
            if not page_text:
                self.logger.warning("No page text content found")
                return []
            
            self.logger.debug(f"Full page text length: {len(page_text)} characters")
            
            # Split the page text into sections for each question
            enhanced_questions = []
            
            for i, question in enumerate(original_questions):
                question_num = question.get('questionNumber', str(i+1))
                
                try:
                    # Look for this question's result in the page text
                    description = self._extract_description_from_page_text(page_text, question_num, question)
                    
                    # Create enhanced question
                    enhanced_question = question.copy()
                    enhanced_question['description'] = description or ''
                    
                    # Try to extract correct answer as well
                    correct_answer = self._extract_correct_answer_from_page_text(page_text, question_num, question)
                    enhanced_question['correct_answer'] = correct_answer or question.get('options', ['Unknown'])[0]
                    
                    enhanced_questions.append(enhanced_question)
                    
                    if description:
                        self.logger.debug(f"Found description for Q{question_num}: {len(description)} characters")
                    else:
                        self.logger.debug(f"No description found for Q{question_num}")
                        
                except Exception as e:
                    self.logger.warning(f"Error processing question {question_num} in full page text: {e}")
                    # Add question with minimal enhancement on error
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = question.get('options', ['Unknown'])[0]
                    enhanced_question['description'] = ''
                    enhanced_questions.append(enhanced_question)
            
            descriptions_found = sum(1 for q in enhanced_questions if q.get('description'))
            self.logger.info(f"Full page text extraction completed: {descriptions_found}/{len(enhanced_questions)} descriptions found")
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.error(f"Error in full page text extraction: {e}")
            return []

    def _extract_description_from_page_text(self, page_text: str, question_num: str, question: Dict[str, Any]) -> Optional[str]:
        """Extract description for a specific question from the full page text."""
        try:
            # Split the page text to find sections for each question
            question_sections = self._split_page_text_by_questions(page_text)
            
            # Try to find the section for this specific question
            if question_num in question_sections:
                section_text = question_sections[question_num]
                description = self._extract_funtrivia_explanation(section_text)
                if description:
                    return description
            
            # Fallback: try to find question-specific content by looking for the question text
            question_text = question.get('question', '').strip()
            if question_text:
                description = self._extract_description_near_question(page_text, question_text)
                if description:
                    return description
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting description for Q{question_num}: {e}")
            return None

    def _extract_correct_answer_from_page_text(self, page_text: str, question_num: str, question: Dict[str, Any]) -> Optional[str]:
        """Extract correct answer for a specific question from the full page text."""
        try:
            # Get question options to validate against
            question_options = question.get('options', [])
            
            # Split page text into sections by question
            question_sections = self._split_page_text_by_questions(page_text)
            
            # Look for correct answer in the specific question's section
            if question_num in question_sections:
                section_text = question_sections[question_num]
                
                # Enhanced patterns to find correct answers
                patterns = [
                    r'The correct answer was\s+([^.\n\r]+)',
                    r'Correct answer was\s+([^.\n\r]+)', 
                    r'correct answer:\s*([^.\n\r]+)',
                    r'The correct answer is\s+([^.\n\r]+)',
                    r'Answer:\s*([^.\n\r]+)',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, section_text, re.IGNORECASE | re.DOTALL)
                    for match in matches:
                        answer_text = match.strip()
                        
                        # Try to match with actual question options
                        for option in question_options:
                            option_clean = option.strip()
                            # Exact match
                            if option_clean.lower() == answer_text.lower():
                                self.logger.debug(f"Found exact correct answer for Q{question_num}: {option_clean}")
                                return option_clean
                            # Partial match (answer contains option or vice versa)
                            elif (option_clean.lower() in answer_text.lower() or 
                                  answer_text.lower() in option_clean.lower()):
                                self.logger.debug(f"Found partial correct answer for Q{question_num}: {option_clean}")
                                return option_clean
                        
                        # If no option match, return the raw answer (might be formatted differently)
                        if answer_text and len(answer_text) > 1:
                            self.logger.debug(f"Found raw correct answer for Q{question_num}: {answer_text}")
                            return answer_text
            
            # Fallback: try to find answer by question context in full page
            # Look for patterns like "1. Your Answer: [No Answer] The correct answer was..."
            question_context_patterns = [
                rf'{question_num}\.\s+.*?The correct answer was\s+([^.\n\r]+)',
                rf'Question {question_num}.*?The correct answer was\s+([^.\n\r]+)',
                rf'{question_num}\.\s+.*?correct answer:\s*([^.\n\r]+)',
            ]
            
            for pattern in question_context_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    answer_text = match.strip()
                    
                    # Validate against question options
                    for option in question_options:
                        option_clean = option.strip()
                        if (option_clean.lower() == answer_text.lower() or
                            option_clean.lower() in answer_text.lower() or 
                            answer_text.lower() in option_clean.lower()):
                            self.logger.debug(f"Found contextual correct answer for Q{question_num}: {option_clean}")
                            return option_clean
                    
                    # Return raw answer if no option match
                    if answer_text and len(answer_text) > 1:
                        self.logger.debug(f"Found contextual raw answer for Q{question_num}: {answer_text}")
                        return answer_text
            
            self.logger.debug(f"No correct answer found for Q{question_num}")
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting correct answer for Q{question_num}: {e}")
            return None
    
    def _split_page_text_by_questions(self, page_text: str) -> Dict[str, str]:
        """Split the page text into sections for each question with improved boundary detection."""
        try:
            sections = {}
            
            # Look for question number patterns like "Question 1", "1.", etc.
            import re
            question_pattern = r'(\d+)\.\s+'
            
            matches = list(re.finditer(question_pattern, page_text, re.MULTILINE | re.IGNORECASE))
            
            for i, match in enumerate(matches):
                # Get question number from the capture group
                question_num = match.group(1)
                if not question_num:
                    continue
                
                # Get the start position of this question's content
                start_pos = match.start()
                
                # Get the end position (start of next question or end of text)
                if i + 1 < len(matches):
                    end_pos = matches[i + 1].start()
                else:
                    end_pos = len(page_text)
                
                # Extract the section text for this question
                raw_section = page_text[start_pos:end_pos].strip()
                
                # Clean up the section to remove cross-contamination
                cleaned_section = self._clean_question_section(raw_section, question_num)
                
                if cleaned_section:
                    sections[question_num] = cleaned_section
                
            self.logger.debug(f"Split page text into {len(sections)} question sections")
            return sections
            
        except Exception as e:
            self.logger.debug(f"Error splitting page text by questions: {e}")
            return {}
    
    def _clean_question_section(self, section_text: str, question_num: str) -> str:
        """Clean a question section to prevent cross-contamination from adjacent questions."""
        try:
            lines = section_text.split('\n')
            cleaned_lines = []
            found_answer = False
            
            for line in lines:
                line_stripped = line.strip()
                
                # Skip empty lines
                if not line_stripped:
                    continue
                
                # Stop if we hit another question number (except our own)
                other_question_match = re.match(r'^(\d+)\.\s+', line_stripped)
                if other_question_match and other_question_match.group(1) != question_num:
                    break
                
                # Stop at navigation elements that indicate end of question content
                if any(marker in line_stripped.lower() for marker in [
                    'next quiz', 'previous quiz', 'back to', 'home page', 'quiz menu',
                    'browse quizzes', 'quiz categories', 'more quizzes'
                ]):
                    break
                
                # Include lines that contain answer patterns
                if 'the correct answer was' in line_stripped.lower():
                    found_answer = True
                    cleaned_lines.append(line)
                    # Continue for a few more lines to capture the explanation
                    continue
                
                # If we found an answer, include next few lines (likely explanation)
                if found_answer and len(cleaned_lines) < 20:  # Reasonable limit
                    cleaned_lines.append(line)
                elif not found_answer:
                    # Before finding answer, include all relevant lines
                    cleaned_lines.append(line)
                else:
                    # After collecting explanation lines, stop
                    break
            
            return '\n'.join(cleaned_lines).strip()
            
        except Exception as e:
            self.logger.debug(f"Error cleaning question section {question_num}: {e}")
            return section_text
    
    def _extract_description_near_question(self, page_text: str, question_text: str) -> Optional[str]:
        """Find description text near a specific question in the page text."""
        try:
            # Find the question text in the page
            question_pos = page_text.lower().find(question_text.lower())
            if question_pos == -1:
                return None
            
            # Look for description patterns within a reasonable distance after the question
            # Typical distance: 500-2000 characters after the question
            search_start = question_pos
            search_end = min(question_pos + 2000, len(page_text))
            search_section = page_text[search_start:search_end]
            
            # Extract description from this localized section
            description = self._extract_funtrivia_explanation(search_section)
            return description
            
        except Exception as e:
            self.logger.debug(f"Error extracting description near question: {e}")
            return None

    async def _extract_from_result_blocks(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract results from structured result blocks on the results page.
        
        PRIMARY EXPLANATION EXTRACTION METHOD:
        ====================================
        This is the main method for extracting explanations/descriptions from FunTrivia results pages.
        It processes structured result blocks to find detailed explanations for each question.
        
        EXPLANATION EXTRACTION PROCESS:
        1. RESULT BLOCK DETECTION:
           - Locates individual result blocks for each question on results page
           - Uses multiple CSS selectors to handle different FunTrivia layouts
           - Ensures we have enough blocks to match all questions
        
        2. EXPLANATION PARSING:
           - Extracts "Interesting Information" sections from each result block
           - Handles multi-paragraph explanations that span multiple elements
           - Processes alternative explanation formats (generic markers, HTML structure)
           - Applies heuristic extraction as fallback for edge cases
        
        3. CSV INTEGRATION:
           - Stores explanations in both "Hint" and "Description" columns for compatibility
           - Cleans and normalizes text for proper CSV storage
           - Leaves fields blank if explanations are missing (logs warnings)
           - Maintains original question data while adding explanation content
        
        4. ERROR HANDLING & STATISTICS:
           - Tracks extraction success rates for explanations and correct answers
           - Logs detailed statistics about how many explanations were found
           - Handles individual question failures gracefully without breaking entire quiz
           - Provides comprehensive logging for debugging and monitoring
        
        MULTI-PARAGRAPH SUPPORT:
        - Captures explanations that span multiple DOM elements
        - Preserves paragraph structure while cleaning formatting
        - Handles various FunTrivia explanation layouts and styles
        """
        try:
            # Try multiple selectors to find result blocks for questions
            result_selectors = [
                '.questionReview',           # Common FunTrivia results class
                '.questionTable',            # Table-based results layout
                '.result-item',              # Generic result item
                '.question-result',          # Question-specific result block
                '.quiz-result-item',         # Alternative quiz result format
                'tr[class*="question"]',     # Table row with question class
                'div[class*="question"]',    # Div with question class
                '.question-block',           # Question block wrapper
                'table tr',                  # All table rows (common on FunTrivia)
                'tr',                        # Generic table rows
                'tr td',                     # Table data cells
                '.quiz tr',                  # Quiz table rows
                '.results tr',               # Results table rows
                'table[class*="quiz"] tr',   # Quiz table with any quiz class
                'table[class*="result"] tr', # Result table with any result class
                '[class*="quiz"] tr',        # Any element with quiz in class name
                '[class*="result"] tr'       # Any element with result in class name
            ]
            
            result_blocks = []
            successful_selector = None
            
            # Find the best selector that gives us enough result blocks
            for selector in result_selectors:
                blocks = await page.query_selector_all(selector)
                if blocks and len(blocks) >= len(original_questions):
                    result_blocks = blocks
                    successful_selector = selector
                    self.logger.debug(f"Found {len(blocks)} result blocks using selector: {selector}")
                    break
                elif blocks:
                    self.logger.debug(f"Found {len(blocks)} result blocks with selector {selector} (need {len(original_questions)})")
            
            if not result_blocks:
                self.logger.warning("No structured result blocks found on results page")
                return []
            
            self.logger.info(f"Extracting results from {len(result_blocks)} structured blocks using selector: {successful_selector}")
            
            enhanced_questions = []
            extraction_stats = {'correct_answers_found': 0, 'explanations_found': 0, 'explanations_missing': 0}
            
            for i, (question, result_block) in enumerate(zip(original_questions, result_blocks)):
                try:
                    question_num = question.get('questionNumber', str(i+1))
                    self.logger.debug(f"Processing result block for question {question_num}")
                    
                    # Extract correct answer from the result block
                    correct_answer = await self._extract_correct_answer_from_block(result_block)
                    if correct_answer:
                        extraction_stats['correct_answers_found'] += 1
                        self.logger.debug(f"Found correct answer for Q{question_num}: {correct_answer[:50]}...")
                    
                    # Extract explanation/description from the result block
                    explanation = await self._extract_explanation_from_block(result_block, question_num)
                    if explanation:
                        extraction_stats['explanations_found'] += 1
                        self.logger.debug(f"Found explanation for Q{question_num}: {len(explanation)} characters")
                    else:
                        extraction_stats['explanations_missing'] += 1
                        self.logger.warning(f"No explanation found for question {question_num}")
                    
                    # Create enhanced question with extracted data
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = correct_answer or question.get('options', ['Unknown'])[0]
                    enhanced_question['hint'] = explanation or ''
                    enhanced_question['description'] = explanation or ''  # Store in both fields for compatibility
                    
                    enhanced_questions.append(enhanced_question)
                    
                except Exception as e:
                    self.logger.error(f"Error processing result block {i} for question {question.get('questionNumber', i+1)}: {e}")
                    # Add question with minimal enhancement on error
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = question.get('options', ['Unknown'])[0]
                    enhanced_question['hint'] = ''
                    enhanced_question['description'] = ''
                    enhanced_questions.append(enhanced_question)
            
            # Log extraction statistics
            self.logger.info(f"Result extraction stats: {extraction_stats['correct_answers_found']}/{len(original_questions)} correct answers, "
                           f"{extraction_stats['explanations_found']}/{len(original_questions)} explanations found")
            
            if extraction_stats['explanations_missing'] > 0:
                self.logger.warning(f"{extraction_stats['explanations_missing']} questions missing explanations")
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.error(f"Error extracting from result blocks: {e}")
            self.logger.debug("Result blocks extraction error details:", exc_info=True)
            return []

    async def _extract_from_text_results(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract results from text-based results format (fallback method).
        
        This method parses the entire page text to find question results when
        structured result blocks are not available. It looks for patterns like:
        - Question numbers followed by correct answers
        - "Interesting Information" or explanation blocks
        - Text patterns that indicate question boundaries
        """
        try:
            self.logger.info("Attempting text-based results extraction (fallback method)")
            
            # Get all text content from the results page
            page_text = await page.evaluate('document.body.innerText')
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            
            enhanced_questions = []
            extraction_stats = {'correct_answers_found': 0, 'explanations_found': 0}
            
            for i, question in enumerate(original_questions):
                question_num = question.get('questionNumber', str(i+1))
                
                try:
                    # Look for this question's results in the text
                    correct_answer = self._find_correct_answer_in_text(lines, question_num, question)
                    explanation = self._find_explanation_in_text(lines, question_num)
                    
                    if correct_answer:
                        extraction_stats['correct_answers_found'] += 1
                    
                    if explanation:
                        extraction_stats['explanations_found'] += 1
                        self.logger.debug(f"Found text-based explanation for Q{question_num}: {len(explanation)} characters")
                    else:
                        self.logger.warning(f"No explanation found in text for question {question_num}")
                    
                    # Create enhanced question
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = correct_answer or question.get('options', ['Unknown'])[0]
                    enhanced_question['hint'] = explanation or ''
                    enhanced_question['description'] = explanation or ''
                    
                    enhanced_questions.append(enhanced_question)
                    
                except Exception as e:
                    self.logger.error(f"Error processing text results for question {question_num}: {e}")
                    # Add question with minimal enhancement on error
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = question.get('options', ['Unknown'])[0]
                    enhanced_question['hint'] = ''
                    enhanced_question['description'] = ''
                    enhanced_questions.append(enhanced_question)
            
            self.logger.info(f"Text extraction stats: {extraction_stats['correct_answers_found']}/{len(original_questions)} correct answers, "
                           f"{extraction_stats['explanations_found']}/{len(original_questions)} explanations found")
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.error(f"Error extracting from text results: {e}")
            self.logger.debug("Text results extraction error details:", exc_info=True)
            return []

    def _find_correct_answer_in_text(self, lines: List[str], question_num: str, question: Dict[str, Any]) -> Optional[str]:
        """
        Find the correct answer for a specific question in the text lines.
        
        Looks for patterns like:
        - "Question X: Correct Answer: [answer]"
        - "1. [answer]" (in results context)
        - Answer options that match the question's options
        """
        try:
            question_options = question.get('options', [])
            
            # Look for explicit correct answer patterns
            for i, line in enumerate(lines):
                line_lower = line.lower()
                
                # Pattern 1: "Question X" followed by correct answer
                if f"question {question_num}" in line_lower or f"{question_num}." in line:
                    # Look in current line and next few lines for answer patterns
                    search_lines = lines[i:i+5]
                    for search_line in search_lines:
                        search_lower = search_line.lower()
                        
                        if any(keyword in search_lower for keyword in ['correct answer:', 'answer:', 'correct:']):
                            # Extract answer after the keyword
                            for keyword in ['correct answer:', 'answer:', 'correct:']:
                                if keyword in search_lower:
                                    potential_answer = search_line[search_lower.index(keyword) + len(keyword):].strip()
                                    # Validate against question options
                                    for option in question_options:
                                        if option.lower() in potential_answer.lower() or potential_answer.lower() in option.lower():
                                            return option
                                    return potential_answer
                
                # Pattern 2: Direct option match in results context
                if f"{question_num}." in line and any(opt.lower() in line_lower for opt in question_options):
                    for option in question_options:
                        if option.lower() in line_lower:
                            return option
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error finding correct answer in text for question {question_num}: {e}")
            return None

    def _find_explanation_in_text(self, lines: List[str], question_num: str) -> Optional[str]:
        """
        Find the explanation/description for a specific question in the text lines.
        
        TEXT-BASED EXPLANATION EXTRACTION (FALLBACK METHOD):
        ===================================================
        When structured result blocks are not available, this method parses raw page text
        to find explanations for individual questions on the results page.
        
        EXPLANATION LOCATIONS IN TEXT:
        - "Interesting Information:" sections after each question result
        - "Explanation:" blocks following correct answers
        - Multi-paragraph descriptions that span several lines
        - Educational text blocks positioned after question numbers
        
        FILTERING STRATEGY:
        - Excludes navigation menus, quiz links, and page elements
        - Focuses on actual educational content related to the question
        - Filters out numbered lists that are clearly navigation
        - Validates content quality before accepting as explanation
        """
        try:
            explanation_parts = []
            in_explanation = False
            explanation_started = False
            
            for i, line in enumerate(lines):
                line_lower = line.lower().strip()
                line_stripped = line.strip()
                
                # Skip empty lines and very short lines
                if len(line_stripped) < 3:
                    continue
                
                # STEP 1: LOCATE THE TARGET QUESTION
                # Find the specific question we're looking for explanations about
                if f"question {question_num}" in line_lower or (f"{question_num}." in line and len(line) < 80):
                    explanation_started = True
                    self.logger.debug(f"Located question {question_num} in text for explanation search")
                    continue
                
                if not explanation_started:
                    continue
                
                # STEP 2: ENHANCED FILTERING OF NON-EXPLANATION CONTENT
                # Filter out navigation, menus, and other page elements
                navigation_patterns = [
                    r'^\d+\.\s+.+\s+(easy|normal|hard|average|difficult)',  # Quiz list items
                    r'^\d+\.\s+[A-Z][a-z]+.*?trivia',                      # Trivia category links
                    r'funtrivia\s+homepage',                               # Site navigation
                    r'copyright\s+funtrivia',                              # Copyright text
                    r'terms\s+&\s+conditions',                            # Legal text
                    r'explore\s+other\s+quizzes',                          # Quiz navigation
                    r'more\s+.*?\s+quizzes',                               # More quiz links
                    r'go\s+to\s+.*?\s+quizzes',                           # Navigation links
                    r'other\s+destinations',                               # Site navigation
                    r'referenced\s+topics',                               # Topic references
                    r'adopted\s+quizzes',                                  # Quiz adoption info
                    r'^\d+\.\s+[A-Z][^.]{10,50}\s+(easy|normal|hard)',    # Numbered quiz titles
                    r'u\.s\.\s+government\s+quizzes',                     # Category navigation
                    r'zip\s+codes\s+average',                             # Quiz title patterns
                    r'collect\s+the\s+century',                           # Quiz title patterns
                ]
                
                # Check if line matches navigation patterns
                is_navigation = any(re.search(pattern, line_lower, re.IGNORECASE) for pattern in navigation_patterns)
                
                if is_navigation:
                    self.logger.debug(f"Filtered out navigation element for Q{question_num}: {line_stripped[:40]}...")
                    continue
                
                # Additional content filtering
                if (line_stripped.startswith(('Home', 'Quiz', 'Browse', 'Search', 'Login', 'Register')) or
                    'click here' in line_lower or
                    'more information' in line_lower or
                    'visit' in line_lower or
                    line_lower.endswith(('quiz', 'quizzes', 'trivia', 'game', 'games')) or
                    re.match(r'^\d+\.\s+[A-Z].*?Average$', line_stripped) or  # Quiz rating patterns
                    re.match(r'^\d+\.\s+.*?\s+(Average|Easy|Normal|Hard)$', line_stripped)):  # Quiz difficulty patterns
                    
                    self.logger.debug(f"Filtered out site element for Q{question_num}: {line_stripped[:40]}...")
                    continue
                
                # STEP 3: FIND EXPLANATION MARKERS
                # Look for various labels that indicate start of explanation content
                explanation_markers = [
                    'interesting information:',   # FunTrivia's standard label
                    'interesting info:',         # Abbreviated version
                    'explanation:',              # Generic explanation label
                    'additional information:',   # Extended info blocks
                    'did you know:',            # Educational facts
                    'fun fact:',                # Interesting facts
                    'background:',              # Context information
                    'note:',                    # Important notes
                    'trivia:',                  # Trivia fact sections (when followed by colon)
                ]
                
                if any(marker in line_lower for marker in explanation_markers):
                    in_explanation = True
                    self.logger.debug(f"Found explanation marker in text for Q{question_num}: {line_stripped[:50]}...")
                    
                    # Extract content after the marker
                    for marker in explanation_markers:
                        if marker in line_lower:
                            marker_index = line_lower.index(marker)
                            text_after_marker = line[marker_index + len(marker):].strip(' :')
                            if text_after_marker and len(text_after_marker) > 10:  # Ensure substantial content
                                explanation_parts.append(text_after_marker)
                            break
                    continue
                
                # STEP 4: COLLECT EXPLANATION CONTENT
                # Gather all explanation text until we hit a stopping condition
                if in_explanation:
                    # Define stopping conditions that indicate end of explanation
                    stop_conditions = [
                        line_lower.startswith('question'),              # Next question started
                        'your score' in line_lower,                     # Score section reached
                        'quiz complete' in line_lower,                  # Quiz completion section
                        'quiz results' in line_lower,                   # Results summary section
                        line_lower.startswith('correct answer:'),       # Another question's answer
                        len(line_stripped) < 10 and line_stripped.isdigit(),  # Standalone question number
                        'submit' in line_lower and 'quiz' in line_lower, # Submit buttons/forms
                        line_lower.startswith('total score'),           # Score summary
                        line_lower.startswith('final score'),           # Final results
                        'next question' in line_lower,                  # Question navigation
                        'previous question' in line_lower,              # Question navigation
                    ]
                    
                    if any(condition for condition in stop_conditions):
                        self.logger.debug(f"Hit stop condition for Q{question_num} explanation: {line_stripped[:30]}...")
                        break
                    
                    # ENHANCED CONTENT VALIDATION
                    # Only collect lines that appear to be actual explanation content
                    if (len(line_stripped) > 15 and  # Ensure substantial content
                        not line_lower.startswith(('a)', 'b)', 'c)', 'd)', 'a.', 'b.', 'c.', 'd.')) and  # Skip answer options
                        not line_lower.startswith('question') and              # Skip question headers
                        'correct answer' not in line_lower and                 # Skip answer declarations
                        not line_lower.startswith(('next', 'previous', 'submit', 'back', 'home')) and  # Skip navigation
                        not re.match(r'^\d+\.\s+', line_stripped) and         # Skip numbered lists
                        not line_lower.endswith(('average', 'easy', 'normal', 'hard', 'difficult')) and  # Skip quiz ratings
                        'funtrivia' not in line_lower and                     # Skip site references
                        'quiz' not in line_lower.split()[-3:] and             # Skip if 'quiz' in last 3 words
                        not re.search(r'\b(browse|search|login|register)\b', line_lower)):  # Skip site actions
                        
                        # Additional quality check: ensure it's educational content
                        educational_indicators = [
                            'because', 'this is', 'the reason', 'actually', 'in fact', 'however',
                            'therefore', 'although', 'since', 'according to', 'research shows',
                            'studies', 'scientists', 'experts', 'discovered', 'found that',
                            'evidence', 'data', 'statistics', 'history', 'historical',
                            'originated', 'invented', 'created', 'established', 'founded'
                        ]
                        
                        # Accept if it contains educational language OR is substantial content
                        if (any(indicator in line_lower for indicator in educational_indicators) or 
                            len(line_stripped) > 50):  # Accept longer content even without indicators
                            
                            explanation_parts.append(line_stripped)
                            self.logger.debug(f"Collected explanation line for Q{question_num}: {line_stripped[:50]}...")
                
                # STEP 5: DETECT NEXT QUESTION BOUNDARY
                # Stop collection if we've moved to the next question
                try:
                    next_question_num = str(int(question_num) + 1)
                    if (f"question {next_question_num}" in line_lower or 
                        (f"{next_question_num}." in line and len(line) < 80)):
                        self.logger.debug(f"Reached next question ({next_question_num}) - stopping explanation collection for Q{question_num}")
                        break
                except ValueError:
                    # Handle non-numeric question numbers gracefully
                    pass
            
            # STEP 6: PROCESS AND VALIDATE COLLECTED EXPLANATION
            # Join collected parts and validate content quality
            if explanation_parts:
                # Join explanation parts with proper spacing for readability
                explanation = ' '.join(explanation_parts).strip()
                
                # Clean up excessive whitespace while preserving structure
                explanation = ' '.join(explanation.split())
                
                # Final quality validation
                if (len(explanation) > 30 and  # Minimum meaningful length
                    not re.match(r'^\d+\.\s+', explanation) and  # Not a numbered list item
                    'average' not in explanation.lower().split()[-2:]):  # Doesn't end with quiz rating terms
                    
                    self.logger.debug(f"Successfully extracted text-based explanation for Q{question_num}: {len(explanation)} chars")
                    return explanation
                else:
                    self.logger.debug(f"Explanation failed quality check for Q{question_num}: {explanation[:100]}...")
            
            # NO EXPLANATION FOUND
            self.logger.debug(f"No text-based explanation found for question {question_num}")
            return None
            
        except Exception as e:
            self.logger.debug(f"Error finding explanation in text for question {question_num}: {e}")
            return None

    async def _extract_correct_answer_from_block(self, result_block) -> Optional[str]:
        """Extract correct answer from a result block."""
        try:
            text = await result_block.inner_text()
            patterns = [
                r'Correct Answer:\s*(.+?)(?:\n|$)',
                r'Answer:\s*(.+?)(?:\n|$)',
                r'Correct:\s*(.+?)(?:\n|$)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                    
        except Exception as e:
            self.logger.debug(f"Error extracting correct answer: {e}")
        return None

    async def _extract_explanation_from_block(self, result_block, question_num: str) -> Optional[str]:
        """
        Extract explanation text from a FunTrivia result block.
        
        FunTrivia results follow this structure:
        1. Question text
        2. Your Answer: [answer]
        3. The correct answer was [answer]
        4. [Explanation paragraphs - this is what we want]
        5. X% of players have answered correctly.
        """
        try:
            # Get all text content from the result block
            block_text = await result_block.inner_text()
            if not block_text or len(block_text.strip()) < 20:
                return None
            
            # Primary strategy: Extract text after "The correct answer was..." until statistics
            explanation = self._extract_funtrivia_explanation(block_text)
            if explanation:
                self.logger.debug(f"Found explanation for Q{question_num}: {len(explanation)} characters")
                return self._clean_explanation_text(explanation)
            
            self.logger.debug(f"No explanation found in result block for Q{question_num}")
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting explanation from block for Q{question_num}: {e}")
            return None

    def _extract_funtrivia_explanation(self, text: str) -> Optional[str]:
        """
        Extract explanation text from FunTrivia results using the actual structure.
        
        FunTrivia structure:
        - Question text
        - Your Answer: [answer]  
        - The correct answer was [answer]
        - [Explanation paragraphs] <- Extract this
        - X% of players have answered correctly
        """
        try:
            # Clean and normalize the text
            text = ' '.join(text.split())
            
            # Primary patterns to match FunTrivia's actual structure
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
            
            for pattern in patterns:
                match = re.search(pattern, text, re.MULTILINE | re.DOTALL | re.IGNORECASE)
                if match:
                    explanation = match.group(1).strip()
                    # Clean up the explanation
                    explanation = re.sub(r'\s+', ' ', explanation)  # Normalize whitespace
                    explanation = explanation.strip()
                    
                    # Filter out obvious non-explanations
                    if self._is_valid_explanation(explanation):
                        return explanation
            
            # Fallback: line-by-line analysis for edge cases
            return self._extract_explanation_line_by_line(text)
            
        except Exception as e:
            self.logger.debug(f"Error in _extract_funtrivia_explanation: {e}")
            return None

    def _extract_explanation_line_by_line(self, text: str) -> Optional[str]:
        """
        Fallback method to extract explanations by analyzing line by line.
        """
        try:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            explanation_lines = []
            found_answer = False
            
            for line in lines:
                # Skip until we find the correct answer line
                if re.search(r'The correct answer was|correct answer:', line, re.IGNORECASE):
                    found_answer = True
                    continue
                
                # If we found the answer, start collecting explanation lines
                if found_answer:
                    # Stop at statistics or navigation
                    if re.search(r'\d+%\s+of\s+players|I see an error|Your Answer:|Question \d+', line, re.IGNORECASE):
                        break
                    # Collect substantial lines (likely part of explanation)
                    if len(line) > 20 and not self._is_navigation_line(line):
                        explanation_lines.append(line)
            
            if explanation_lines:
                explanation = ' '.join(explanation_lines).strip()
                if self._is_valid_explanation(explanation):
                    return explanation
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error in line-by-line extraction: {e}")
            return None

    def _is_valid_explanation(self, text: str) -> bool:
        """Check if extracted text is a valid explanation."""
        if not text or len(text.strip()) < 30:
            return False
        
        text_lower = text.lower().strip()
        
        # Reject obvious non-explanations
        invalid_indicators = [
            'funtrivia', 'homepage', 'browse quizzes', 'click here',
            'visit our', 'explore other', 'more quizzes'
        ]
        
        if any(indicator in text_lower for indicator in invalid_indicators):
            return False
        
        # Must have reasonable length and educational content
        return len(text) >= 30 and len(text.split()) >= 8

    def _is_navigation_line(self, line: str) -> bool:
        """Check if a line is navigation/menu content."""
        line_lower = line.lower()
        nav_indicators = [
            'funtrivia', 'homepage', 'browse', 'click here', 'visit',
            'explore', 'more quizzes', 'trivia quiz', 'average quiz'
        ]
        return any(indicator in line_lower for indicator in nav_indicators)
    
    def _validate_explanation_quality(self, text: str) -> bool:
        """
        Validate that extracted text is actually an explanation, not navigation.
        
        EXPLANATION QUALITY VALIDATION:
        =============================
        This function ensures extracted text is educational content rather than
        navigation menus, quiz lists, or other page elements.
        """
        if not text or len(text.strip()) < 30:
            return False
        
        text_lower = text.lower().strip()
        
        # Reject if it looks like navigation or quiz lists
        navigation_indicators = [
            r'^\d+\.\s+.+\s+(average|easy|normal|hard|difficult)$',  # Quiz ratings
            r'^\d+\.\s+[A-Z][a-z]+.*?trivia',                       # Trivia categories
            r'funtrivia\s+homepage',                                # Site navigation
            r'browse\s+quizzes',                                    # Quiz browsing
            r'more\s+.*?\s+quizzes',                               # More quiz links
            r'explore\s+other\s+quizzes',                          # Quiz exploration
            r'click\s+here\s+to',                                  # Click instructions
            r'visit\s+our',                                        # Site promotion
        ]
        
        if any(re.search(pattern, text_lower, re.IGNORECASE) for pattern in navigation_indicators):
            return False
        
        # Reject if it's just quiz titles or category lists
        if (text_lower.endswith(('quiz', 'quizzes', 'trivia', 'average', 'easy', 'normal', 'hard')) or
            re.match(r'^\d+\.\s+', text.strip()) or  # Starts with number
            'funtrivia' in text_lower or
            len(text.split()) < 8):  # Too short to be meaningful explanation
            return False
        
        # Accept if it contains educational language
        educational_indicators = [
            'because', 'this is', 'the reason', 'actually', 'in fact', 'however',
            'therefore', 'although', 'since', 'according to', 'research shows',
            'studies', 'scientists', 'experts', 'discovered', 'found that',
            'evidence', 'data', 'statistics', 'history', 'historical',
            'originated', 'invented', 'created', 'established', 'founded',
            'named after', 'known for', 'famous for', 'designed by', 'built in'
        ]
        
        return any(indicator in text_lower for indicator in educational_indicators)

    def _extract_interesting_information(self, text: str) -> Optional[str]:
        """
        Extract text from "Interesting Information" sections.
        
        FUNTIVIA'S STANDARD EXPLANATION FORMAT:
        ====================================== 
        FunTrivia commonly uses "Interesting Information:" as the label for
        question explanations. This method finds and extracts that content.
        
        MULTI-PARAGRAPH SUPPORT:
        - Captures content that spans multiple lines/paragraphs
        - Handles various formatting styles (with/without colons, spacing)
        - Preserves meaningful text structure while cleaning formatting artifacts
        
        PATTERN MATCHING:
        - Case-insensitive matching for flexibility
        - Multiple regex patterns to handle formatting variations
        - Stops at logical boundaries (next question, score sections, etc.)
        """
        try:
            # Enhanced patterns for multi-paragraph "Interesting Information" extraction
            patterns = [
                # Standard format with colon - multi-paragraph capture
                r'Interesting Information:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                # Alternative format without colon
                r'Interesting Information\s+(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                # Abbreviated format
                r'Interesting Info:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                # Block format (starts on new line after label)
                r'(?:^|\n)Interesting Information[:\s]*\n(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                # Extended pattern to capture longer explanations
                r'Interesting Information[:\s]*(.+?)(?=\n(?:Question \d+|Your Score|Quiz Results|Submit|Next Question)|\Z)',
                # More flexible patterns for FunTrivia variations
                r'(?i)interesting[:\s]*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'(?i)info[:\s]*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'(?i)trivia[:\s]*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                # Capture any substantive paragraph after correct answer indicators
                r'(?i)correct[:\s]+[^.]+\.(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'(?i)answer[:\s]+[^.]+\.(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    explanation = match.group(1).strip()
                    
                    # Enhanced cleaning for multi-paragraph content
                    explanation = self._clean_explanation_text(explanation)
                    
                    # Validation: ensure meaningful content length
                    if len(explanation) > 20:  # Minimum meaningful length
                        self.logger.debug(f"Extracted Interesting Information: {len(explanation)} chars")
                        return explanation
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting interesting information: {e}")
            return None

    def _extract_generic_explanation(self, text: str) -> Optional[str]:
        """
        Extract explanations using generic markers like "Explanation:", "Info:", etc.
        
        ALTERNATIVE EXPLANATION FORMATS:
        ===============================
        Handles cases where FunTrivia uses different labels for explanations:
        - "Explanation:" - Direct explanation blocks
        - "Additional Information:" - Supplementary details  
        - "Fun Fact:" - Interesting trivia related to the answer
        - "Background:" - Contextual information
        - "Did you know?" - Educational facts
        
        MULTI-PARAGRAPH EXTRACTION:
        - Captures complete explanation blocks even when spanning multiple paragraphs
        - Handles various separators and formatting styles
        - Maintains readability while normalizing for CSV storage
        """
        try:
            # Enhanced patterns for multi-paragraph generic explanation extraction
            patterns = [
                # Standard explanation formats with enhanced multi-paragraph capture
                r'Explanation:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Info:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Additional Information:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Details:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Trivia:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                
                # Question-style explanation patterns
                r'Did you know[?:]?\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Fun fact[?:]?\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Fun Fact[?:]?\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                
                # Contextual information patterns
                r'Background:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'Context:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                r'More Info:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z|Your Score|Quiz Complete))',
                
                # Extended patterns for longer explanations
                r'(?:Explanation|Additional Information|Details)[:\s]*(.+?)(?=\n(?:Question \d+|Your Score|Quiz Results|Submit|Next Question)|\Z)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    explanation = match.group(1).strip()
                    
                    # Enhanced cleaning for multi-paragraph content
                    explanation = self._clean_explanation_text(explanation)
                    
                    # Validation for meaningful content
                    if len(explanation) > 20:
                        self.logger.debug(f"Extracted generic explanation: {len(explanation)} chars")
                        return explanation
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting generic explanation: {e}")
            return None

    async def _extract_explanation_from_html_structure(self, result_block) -> Optional[str]:
        """
        Extract explanation by analyzing the HTML structure of the result block.
        
        HTML STRUCTURE ANALYSIS:
        =======================
        When text-based parsing fails, this method analyzes the DOM structure:
        
        CSS CLASS DETECTION:
        - Looks for explanation-specific CSS classes
        - Searches for elements with 'explanation', 'interesting', 'info' in class names
        - Handles various FunTrivia layout formats
        
        POSITIONAL ANALYSIS:
        - Finds text blocks that appear after "Correct Answer" sections
        - Identifies substantial content blocks likely to be explanations
        - Filters out navigation/UI elements
        
        MULTI-PARAGRAPH PRESERVATION:
        - Extracts content from multiple DOM elements if needed
        - Combines adjacent explanation elements
        - Maintains paragraph structure through proper spacing
        """
        try:
            # APPROACH 1: Look for explanation-specific CSS classes and elements
            explanation_selectors = [
                # Specific explanation classes
                '.explanation',
                '.interesting-info', 
                '.interesting-information',
                '.additional-info',
                '.trivia-info',
                '.trivia-fact',
                '.fun-fact',
                '.background-info',
                '.question-explanation',
                '.answer-explanation',
                
                # Text-content based selectors (Playwright syntax)
                'p:has-text("Interesting")',
                'div:has-text("Interesting")',
                'p:has-text("Explanation")',
                'div:has-text("Explanation")',
                
                # Generic class pattern matching
                '[class*="explanation"]',
                '[class*="interesting"]',
                '[class*="info"]',
                '[class*="trivia"]'
            ]
            
            for selector in explanation_selectors:
                try:
                    explanation_elements = await result_block.query_selector_all(selector)
                    if explanation_elements:
                        # Combine text from all matching elements (handles multi-paragraph)
                        explanation_parts = []
                        for element in explanation_elements:
                            element_text = await element.inner_text()
                            if element_text and len(element_text.strip()) > 20:
                                explanation_parts.append(element_text.strip())
                        
                        if explanation_parts:
                            # Join multiple paragraphs with proper spacing
                            combined_explanation = ' '.join(explanation_parts)
                            cleaned_explanation = self._clean_explanation_text(combined_explanation)
                            if len(cleaned_explanation) > 20:
                                self.logger.debug(f"Found structured explanation via selector '{selector}': {len(cleaned_explanation)} chars")
                                return cleaned_explanation
                except Exception:
                    continue
            
            # APPROACH 2: Positional analysis - find substantial text after "Correct Answer"
            # This handles cases where explanations don't have specific CSS classes
            try:
                all_elements = await result_block.query_selector_all('p, div, span')
                found_correct_answer = False
                explanation_candidates = []
                
                for element in all_elements:
                    element_text = await element.inner_text()
                    element_text_clean = element_text.strip()
                    element_text_lower = element_text_clean.lower()
                    
                    # Mark when we pass the correct answer section
                    if any(phrase in element_text_lower for phrase in ['correct answer', 'answer:', 'correct:']):
                        found_correct_answer = True
                        continue
                    
                    # Collect substantial explanation text after correct answer
                    if (found_correct_answer and 
                        len(element_text_clean) > 30 and  # Substantial content
                        not any(skip_phrase in element_text_lower for skip_phrase in 
                               ['question', 'q.', 'your score', 'submit', 'next', 'previous', 'quiz result'])):
                        
                        explanation_candidates.append(element_text_clean)
                        
                        # Stop if we find a good amount of content
                        if len(' '.join(explanation_candidates)) > 100:
                            break
                
                # Process collected explanation candidates
                if explanation_candidates:
                    combined_explanation = ' '.join(explanation_candidates)
                    cleaned_explanation = self._clean_explanation_text(combined_explanation)
                    if len(cleaned_explanation) > 20:
                        self.logger.debug(f"Found positional explanation: {len(cleaned_explanation)} chars")
                        return cleaned_explanation
                
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting explanation from HTML structure: {e}")
            return None

    def _extract_heuristic_explanation(self, text: str) -> Optional[str]:
        """
        Extract explanation using heuristic methods when explicit markers are not found.
        
        This method looks for substantial text blocks that likely contain explanations
        based on their position and content characteristics.
        """
        try:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            # STRATEGY 1: Look for text after correct answer indicators
            explanation_candidates = []
            found_correct_answer = False
            
            for line in lines:
                line_lower = line.lower()
                
                # Mark when we pass the correct answer line
                if any(phrase in line_lower for phrase in [
                    'correct answer', 'answer:', 'correct:', 'the answer is', 'solution:'
                ]):
                    found_correct_answer = True
                    continue
                
                # Skip question headers and short lines
                if (line_lower.startswith(('question', 'q.')) or 
                    len(line) < 25 or
                    line_lower.startswith(('your score', 'submit', 'next question'))):
                    continue
                
                # Collect substantial text that comes after the correct answer
                if (found_correct_answer and 
                    len(line) > 30 and
                    not line.lower().startswith(('a)', 'b)', 'c)', 'd)')) and  # Not answer options
                    not line.isdigit()):  # Not just numbers
                    
                    explanation_candidates.append(line)
            
            # Join explanation candidates and validate
            if explanation_candidates:
                explanation = ' '.join(explanation_candidates)
                explanation = self._clean_explanation_text(explanation)
                
                # Validate that this looks like an explanation (not just random text)
                if (len(explanation) > 50 and 
                    not explanation.lower().startswith('question') and
                    ' ' in explanation):  # Contains spaces (not just a single word)
                    return explanation
            
            # STRATEGY 2: Look for any substantial educational content
            for line in lines:
                line_lower = line.lower()
                
                # Skip navigation and short content
                if (len(line) < 40 or
                    any(skip_word in line_lower for skip_word in [
                        'funtrivia', 'quiz', 'homepage', 'browse', 'click here',
                        'visit our', 'more quizzes', 'explore other', 'return to',
                        'submit', 'next question', 'previous question'
                    ])):
                    continue
                
                # Look for educational indicators
                if any(indicator in line_lower for indicator in [
                    'because', 'this is', 'actually', 'in fact', 'the reason',
                    'according to', 'research', 'studies', 'scientists', 'experts',
                    'discovered', 'evidence', 'history', 'historical', 'originated',
                    'invented', 'created', 'established', 'founded', 'named after',
                    'known for', 'famous for', 'designed by', 'built in', 'located in',
                    'during', 'when', 'where', 'why', 'how', 'first', 'originally',
                    'also known as', 'called', 'means', 'refers to', 'comes from'
                ]):
                    cleaned = self._clean_explanation_text(line)
                    if len(cleaned) > 50:
                        return cleaned
            
            # STRATEGY 3: Look for any substantive paragraph (last resort)
            for line in lines:
                line_lower = line.lower()
                
                # Must be substantial and not navigation
                if (len(line) > 80 and  # Longer text more likely to be explanation
                    not any(skip_pattern in line_lower for skip_pattern in [
                        'funtrivia', 'quiz', 'homepage', 'browse', 'click here',
                        'visit our', 'more quizzes', 'explore other', 'return to',
                        'submit', 'next question', 'previous question', 'score'
                    ]) and
                    # Must look like descriptive text (has common words)
                    sum(1 for word in ['the', 'a', 'an', 'is', 'was', 'are', 'were', 'has', 'have']
                        if word in line_lower.split()) >= 2):
                    
                    cleaned = self._clean_explanation_text(line)
                    if len(cleaned) > 60:
                        return cleaned
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting heuristic explanation: {e}")
            return None

    async def _enhance_questions_basic(self, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Basic enhancement of questions when results page extraction fails."""
        enhanced_questions = []
        
        for question in original_questions:
            enhanced_question = question.copy()
            enhanced_question['correct_answer'] = question.get('options', ['Unknown'])[0]
            enhanced_question['hint'] = ''
            enhanced_question['description'] = ''
            enhanced_questions.append(enhanced_question)
        
        return enhanced_questions

    def _clean_explanation_text(self, text: str) -> str:
        """
        Clean and normalize explanation text for CSV storage.
        
        EXPLANATION TEXT CLEANING PROCESS:
        =================================
        This function processes raw explanation text extracted from results pages
        to ensure clean, consistent formatting suitable for CSV storage.
        
        CLEANING OPERATIONS:
        1. WHITESPACE NORMALIZATION:
           - Removes excessive whitespace and normalizes line breaks
           - Converts multiple spaces to single spaces
           - Trims leading/trailing whitespace and punctuation
        
        2. FORMATTING ARTIFACT REMOVAL:
           - Removes common HTML/web formatting remnants
           - Cleans up duplicate spacing from DOM text extraction
           - Handles line break artifacts from page parsing
        
        3. LABEL PREFIX REMOVAL:
           - Strips explanation labels that may have been included in extraction
           - Removes markers like "Interesting Information:", "Explanation:", etc.
           - Ensures only the actual explanation content remains
        
        4. CSV COMPATIBILITY:
           - Ensures text is safe for CSV storage (no problematic characters)
           - Maintains readability while being storage-friendly
           - Preserves meaningful content structure
        
        MULTI-PARAGRAPH PRESERVATION:
        - Maintains logical flow of multi-paragraph explanations
        - Joins paragraphs with appropriate spacing
        - Preserves sentence structure and readability
        """
        if not text:
            return ""
        
        # STEP 1: WHITESPACE NORMALIZATION
        # Remove excessive whitespace and normalize line breaks to single spaces
        text = ' '.join(text.split())
        
        # STEP 2: FORMATTING ARTIFACT REMOVAL  
        # Clean up common formatting issues from DOM text extraction
        text = text.replace('  ', ' ')  # Remove double spaces
        text = text.strip(' .,;:')      # Remove leading/trailing punctuation and spaces
        
        # STEP 3: EXPLANATION LABEL PREFIX REMOVAL
        # Remove explanation markers that may have been captured during extraction
        prefixes_to_remove = [
            'Interesting Information:',
            'Interesting Info:',
            'Explanation:',
            'Info:',
            'Additional Information:',
            'Details:',
            'Trivia:',
            'Did you know:',
            'Did you know?',
            'Fun fact:',
            'Fun Fact:',
            'Background:',
            'Context:',
            'More Info:'
        ]
        
        # Remove any of these prefixes if they appear at the start of the text
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                self.logger.debug(f"Removed explanation prefix: {prefix}")
                break
        
        # STEP 4: FINAL CLEANUP AND VALIDATION
        # Ensure the cleaned text is properly formatted for CSV storage
        cleaned_text = text.strip()
        
        # Log cleaning results for debugging
        if len(cleaned_text) != len(text.strip()):
            self.logger.debug(f"Explanation cleaning: {len(text.strip())} -> {len(cleaned_text)} chars")
        
        return cleaned_text

    def _extract_audio_url(self, question_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract audio URL from question data using various possible keys.
        
        Args:
            question_data: Question dictionary that may contain audio information
            
        Returns:
            Audio URL if found, None otherwise
        """
        # Check various possible audio URL keys
        audio_keys = ['audioUrl', 'audio_path', 'audio_url', 'mediaUrl', 'media_url']
        
        for key in audio_keys:
            if key in question_data and question_data[key]:
                url = question_data[key]
                # Ensure it's a valid URL, not a local path
                if url.startswith(('http://', 'https://')):
                    return url
        
        return None

    def _get_random_user_agent(self) -> str:
        """Get a random user agent string."""
        return random.choice(USER_AGENTS)

    def get_unmapped_values(self) -> Dict[str, set]:
        """
        Get all values that have been encountered but not found in mappings.
        
        This is useful for debugging and identifying missing mappings that should
        be added to the configuration file. Call this after scraping to see
        what values were not mapped.
        
        Returns:
            Dictionary with 'difficulty', 'domain', and 'topic' keys containing 
            sets of unmapped values encountered during scraping
        """
        return self.scraper_config.get_unmapped_values()
    
    def get_mapping_stats(self) -> Dict[str, Dict[str, int]]:
        """Get statistics about mapping usage."""
        return self.scraper_config.get_mapping_stats()

    async def download_media(self, url: str, media_type: str, question_id: str) -> str:
        """Download media (image/audio) and return the local path."""
        try:
            media_ref = MediaReference(url=url, media_type=media_type, question_id=question_id)
            return await self.media_handler.download_media(media_ref)
        except Exception as e:
            self.logger.error(f"Failed to download media for question {question_id}: {e}")
            return ""

    async def _extract_photo_quiz_questions(self, page: Page) -> List[Dict[str, Any]]:
        """Extract questions from Photo Quiz format with image handling."""
        try:
            questions = await page.evaluate("""
                () => {
                    const questions = [];
                    
                    // Look for question patterns in Photo Quiz format
                    const questionElements = document.querySelectorAll('b, strong, .question');
                    
                    questionElements.forEach((qEl, index) => {
                        const text = qEl.textContent.trim();
                        
                        // Check if this looks like a numbered question
                        const questionMatch = text.match(/^(\\d+)\\.(.*)/);
                        if (questionMatch) {
                            const questionNumber = questionMatch[1];
                            const questionText = questionMatch[2].trim();
                            
                            // Find associated image near this question
                            let associatedImage = null;
                            let current = qEl;
                            
                            // Look for images in the vicinity of the question
                            for (let i = 0; i < 5; i++) {
                                if (current.nextElementSibling) {
                                    current = current.nextElementSibling;
                                    const img = current.querySelector('img') || 
                                               (current.tagName === 'IMG' ? current : null);
                                    
                                    if (img && img.src && !img.src.includes('icon') && 
                                        !img.src.includes('button') && img.width > 50) {
                                        associatedImage = img.src;
                                        break;
                                    }
                                }
                            }
                            
                            // Find radio buttons for this question
                            const radioInputs = document.querySelectorAll(`input[name="q${questionNumber}"]`);
                            const options = Array.from(radioInputs).map(radio => radio.value).filter(v => v);
                            
                            if (questionText && options.length >= 2) {
                                questions.push({
                                    question: questionText,
                                    options: options,
                                    questionNumber: questionNumber,
                                    imageUrl: associatedImage,
                                    isPhotoQuiz: true
                                });
                            }
                        }
                    });
                    
                    return questions;
                }
            """)
            
            # Store image information for later download with proper localization key
            # Final media files are downloaded in _process_extracted_questions with correct keys
            for question in questions:
                if question.get('imageUrl'):
                    self.logger.info(f"Found image for question {question['questionNumber']}: {question['imageUrl']}")
            
            self.logger.info(f"Extracted {len(questions)} photo quiz questions")
            return questions
            
        except Exception as e:
            self.logger.error(f"Error extracting photo quiz questions: {e}")
            return [] 

    async def _extract_audio_quiz_questions(self, page: Page) -> List[Dict[str, Any]]:
        """Extract questions from Audio Quiz format with audio handling."""
        try:
            questions = await page.evaluate("""
                () => {
                    const questions = [];
                    
                    // Look for question patterns in Audio Quiz format
                    const questionElements = document.querySelectorAll('b, strong, .question');
                    
                    questionElements.forEach((qEl, index) => {
                        const text = qEl.textContent.trim();
                        
                        // Check if this looks like a numbered question
                        const questionMatch = text.match(/^(\\d+)\\.(.*)/);
                        if (questionMatch) {
                            const questionNumber = questionMatch[1];
                            const questionText = questionMatch[2].trim();
                            
                            // Find associated audio elements near this question
                            let associatedAudio = null;
                            let current = qEl;
                            
                            // Look for audio elements in the vicinity of the question
                            for (let i = 0; i < 10; i++) {
                                if (current.nextElementSibling) {
                                    current = current.nextElementSibling;
                                    
                                    // Check for direct audio elements
                                    const audio = current.querySelector('audio') || 
                                                 (current.tagName === 'AUDIO' ? current : null);
                                    if (audio && audio.src) {
                                        associatedAudio = audio.src;
                                        break;
                                    }
                                    
                                    // Check for embedded audio (Flash, etc.)
                                    const embed = current.querySelector('embed[src*=".mp3"], embed[src*=".wav"]') ||
                                                 (current.tagName === 'EMBED' && (current.src.includes('.mp3') || current.src.includes('.wav')) ? current : null);
                                    if (embed && embed.src) {
                                        associatedAudio = embed.src;
                                        break;
                                    }
                                    
                                    // Check for object elements with audio data
                                    const object = current.querySelector('object[data*=".mp3"], object[data*=".wav"]') ||
                                                  (current.tagName === 'OBJECT' && (current.data.includes('.mp3') || current.data.includes('.wav')) ? current : null);
                                    if (object && object.data) {
                                        associatedAudio = object.data;
                                        break;
                                    }
                                    
                                    // Check for links to audio files
                                    const audioLink = current.querySelector('a[href*=".mp3"], a[href*=".wav"], a[href*=".ogg"]');
                                    if (audioLink && audioLink.href) {
                                        associatedAudio = audioLink.href;
                                        break;
                                    }
                                }
                            }
                            
                            // Find radio buttons for this question
                            const radioInputs = document.querySelectorAll(`input[name="q${questionNumber}"]`);
                            const options = Array.from(radioInputs).map(radio => radio.value).filter(v => v);
                            
                            if (questionText && options.length >= 2) {
                                questions.push({
                                    question: questionText,
                                    options: options,
                                    questionNumber: questionNumber,
                                    audioUrl: associatedAudio,
                                    isAudioQuestion: true,
                                    isAudioQuiz: true
                                });
                            }
                        }
                    });
                    
                    return questions;
                }
            """)
            
            # Store audio information for later download with proper localization key
            # Final media files are downloaded in _process_extracted_questions with correct keys
            for question in questions:
                if question.get('audioUrl'):
                    self.logger.info(f"Found audio for question {question['questionNumber']}: {question['audioUrl']}")
            
            self.logger.info(f"Extracted {len(questions)} audio quiz questions")
            return questions
            
        except Exception as e:
            self.logger.error(f"Error extracting audio quiz questions: {e}")
            return []

    async def _extract_questions_robust(self, page: Page) -> List[Dict[str, Any]]:
        """Extract questions from standard quiz formats with robust parsing."""
        try:
            questions = await page.evaluate("""
                () => {
                    const questions = [];
                    
                    // Strategy 1: Look for numbered questions
                    const questionElements = document.querySelectorAll('b, strong, .question, h3, h4');
                    
                    questionElements.forEach((qEl, index) => {
                        const text = qEl.textContent.trim();
                        
                        // Check if this looks like a numbered question
                        const questionMatch = text.match(/^(\\d+)\\.(.*)/);
                        if (questionMatch) {
                            const questionNumber = questionMatch[1];
                            const questionText = questionMatch[2].trim();
                            
                            // Find radio buttons for this question
                            const radioInputs = document.querySelectorAll(`input[name="q${questionNumber}"]`);
                            const options = Array.from(radioInputs).map(radio => radio.value).filter(v => v);
                            
                            if (questionText && options.length >= 2) {
                                questions.push({
                                    question: questionText,
                                    options: options,
                                    questionNumber: questionNumber
                                });
                            }
                        }
                    });
                    
                    // Strategy 2: If no numbered questions found, look for form-based structure
                    if (questions.length === 0) {
                        const allRadios = document.querySelectorAll('input[type="radio"]');
                        const questionGroups = {};
                        
                        // Group radio buttons by name
                        allRadios.forEach(radio => {
                            const name = radio.name;
                            if (name) {
                                if (!questionGroups[name]) {
                                    questionGroups[name] = [];
                                }
                                if (radio.value && radio.value.trim()) {
                                    questionGroups[name].push(radio.value.trim());
                                }
                            }
                        });
                        
                        // Create questions from grouped radio buttons
                        Object.keys(questionGroups).forEach((name, index) => {
                            const options = questionGroups[name];
                            if (options.length >= 2) {
                                // Try to find question text near the radio buttons
                                const firstRadio = document.querySelector(`input[name="${name}"]`);
                                let questionText = `Question ${index + 1}`;
                                
                                if (firstRadio) {
                                    // Look for question text before the radio buttons
                                    let current = firstRadio.parentElement;
                                    for (let i = 0; i < 5 && current; i++) {
                                        const textElements = current.querySelectorAll('b, strong, .question');
                                        if (textElements.length > 0) {
                                            const potentialQuestion = textElements[textElements.length - 1].textContent.trim();
                                            if (potentialQuestion.length > 10 && potentialQuestion.includes('?')) {
                                                questionText = potentialQuestion;
                                                break;
                                            }
                                        }
                                        current = current.previousElementSibling;
                                    }
                                }
                                
                                questions.push({
                                    question: questionText,
                                    options: options,
                                    questionNumber: (index + 1).toString()
                                });
                            }
                        });
                    }
                    
                    return questions;
                }
            """)
            
            self.logger.info(f"Extracted {len(questions)} questions using robust extraction")
            return questions
            
        except Exception as e:
            self.logger.error(f"Error in robust question extraction: {e}")
            return []

    async def _extract_hint_from_block(self, result_block) -> Optional[str]:
        """
        Legacy method for extracting hint/explanation from a result block.
        
        This method is maintained for backward compatibility but now delegates
        to the more comprehensive _extract_explanation_from_block method.
        """
        try:
            # Use the enhanced explanation extraction method
            explanation = await self._extract_explanation_from_block(result_block, "unknown")
            return explanation
            
        except Exception as e:
            self.logger.debug(f"Error extracting hint: {e}")
            return None

    async def _diagnose_quiz_page(self, page: Page, quiz_url: str) -> Dict[str, Any]:
        """
        Diagnose quiz page structure for debugging purposes.
        
        QUIZ PAGE DIAGNOSTIC TOOL:
        =========================
        This function analyzes the quiz page structure to help identify
        why breadcrumb extraction or answer selection might be failing.
        """
        try:
            diagnosis = await page.evaluate("""
                () => {
                    const analysis = {
                        url: window.location.href,
                        title: document.title,
                        breadcrumbs: [],
                        radioButtons: 0,
                        formElements: 0,
                        navigation: [],
                        pageStructure: {}
                    };
                    
                    // Analyze breadcrumb structures
                    const breadcrumbSelectors = [
                        '.breadcrumb', '.breadcrumbs', 'nav.breadcrumb', 
                        '#breadcrumb', '.trail', '.page-trail'
                    ];
                    
                    breadcrumbSelectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            elements.forEach(el => {
                                analysis.breadcrumbs.push({
                                    selector: selector,
                                    text: el.textContent.trim(),
                                    links: Array.from(el.querySelectorAll('a')).map(a => ({
                                        text: a.textContent.trim(),
                                        href: a.href
                                    }))
                                });
                            });
                        }
                    });
                    
                    // Analyze radio buttons and form structure
                    const radios = document.querySelectorAll('input[type="radio"]');
                    analysis.radioButtons = radios.length;
                    
                    const radiosByName = {};
                    radios.forEach(radio => {
                        const name = radio.name || 'unnamed';
                        if (!radiosByName[name]) radiosByName[name] = [];
                        radiosByName[name].push({
                            value: radio.value,
                            checked: radio.checked,
                            visible: radio.offsetParent !== null
                        });
                    });
                    analysis.radioGroups = radiosByName;
                    
                    // Analyze forms
                    const forms = document.querySelectorAll('form');
                    analysis.formElements = forms.length;
                    
                    // Analyze navigation structure
                    const navElements = document.querySelectorAll('nav, .nav, .navigation');
                    navElements.forEach((nav, index) => {
                        analysis.navigation.push({
                            index: index,
                            text: nav.textContent.trim().substring(0, 200),
                            links: Array.from(nav.querySelectorAll('a')).map(a => a.textContent.trim()).slice(0, 10)
                        });
                    });
                    
                    // Basic page structure analysis
                    analysis.pageStructure = {
                        hasQuestions: !!document.querySelector('b, strong, .question, h3, h4'),
                        hasImages: document.querySelectorAll('img').length,
                        hasAudio: document.querySelectorAll('audio, embed[src*=".mp3"]').length,
                        loginRequired: document.body.textContent.toLowerCase().includes('log in') || 
                                      document.body.textContent.toLowerCase().includes('sign in')
                    };
                    
                    return analysis;
                }
            """)
            
            # Log key diagnostic information
            self.logger.debug(f"Quiz page diagnosis for {quiz_url}:")
            self.logger.debug(f"  Title: {diagnosis['title']}")
            self.logger.debug(f"  Radio buttons found: {diagnosis['radioButtons']}")
            self.logger.debug(f"  Form elements: {diagnosis['formElements']}")
            self.logger.debug(f"  Breadcrumb elements: {len(diagnosis['breadcrumbs'])}")
            self.logger.debug(f"  Login required: {diagnosis['pageStructure']['loginRequired']}")
            
            # Log breadcrumb details if available
            if diagnosis['breadcrumbs']:
                for breadcrumb in diagnosis['breadcrumbs']:
                    self.logger.debug(f"    Breadcrumb ({breadcrumb['selector']}): {breadcrumb['text'][:100]}")
            
            # Log radio button groups
            if diagnosis['radioGroups']:
                for name, radios in diagnosis['radioGroups'].items():
                    self.logger.debug(f"    Radio group '{name}': {len(radios)} options")
            
            return diagnosis
            
        except Exception as e:
            self.logger.error(f"Error during quiz page diagnosis: {e}")
            return {}

    async def _save_questions_incrementally(self, questions: List[Dict[str, Any]], quiz_log_id: str = "") -> int:
        """
        Save questions immediately after processing each quiz.
        
        INCREMENTAL SAVING STRATEGY:
        ===========================
        This function saves questions to CSV files immediately after each quiz is completed,
        preventing data loss if the scraper is interrupted or encounters errors.
        
        Benefits:
        - Progress is preserved even if scraper is interrupted
        - Reduces memory usage by not accumulating all questions
        - Provides immediate feedback on successful saves
        - Prevents loss of work due to network issues or timeouts
        
        Args:
            questions: List of processed questions from a single quiz
            quiz_log_id: Quiz identifier for logging
            
        Returns:
            Number of questions successfully saved
        """
        if not questions or not self.csv_handler:
            return 0
        
        saved_count = 0
        
        try:
            # Import formatting function
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
            from main import format_question_data_enhanced
            
            # Group questions by type for proper CSV structure
            questions_by_type = {
                'multiple_choice': [],
                'true_false': [],
                'sound': []
            }
            
            # Format and group questions
            for question in questions:
                try:
                    formatted_question = format_question_data_enhanced(question)
                    question_type = question.get('type', 'multiple_choice')
                    questions_by_type[question_type].append(formatted_question)
                    
                    self.logger.debug(f"[{quiz_log_id}] Formatted {question_type} question: {formatted_question.get('Key')}")
                    
                except Exception as e:
                    self.logger.error(f"[{quiz_log_id}] Error formatting question {question.get('id', 'unknown')}: {e}")
                    continue
            
            # Save each question type to its respective CSV file
            csv_files = self.config['storage']['csv_files']
            
            for question_type, type_questions in questions_by_type.items():
                if not type_questions:
                    continue
                
                try:
                    csv_file = csv_files[question_type]
                    new_count = self.csv_handler.append_to_csv(type_questions, csv_file, question_type)
                    saved_count += new_count
                    
                    if new_count > 0:
                        self.logger.info(f"[{quiz_log_id}] ✅ Saved {new_count} {question_type} questions to {csv_file}")
                        
                        # Log sample for verification including description status
                        sample = type_questions[0]
                        description_length = len(sample.get('Description', ''))
                        self.logger.debug(f"[{quiz_log_id}] Sample saved: Key={sample.get('Key')}, Question={sample.get('Question', '')[:50]}...")
                        self.logger.debug(f"[{quiz_log_id}] Sample description: {description_length} chars")
                    
                except Exception as e:
                    self.logger.error(f"[{quiz_log_id}] ❌ Failed to save {question_type} questions: {e}")
                    continue
            
            if saved_count > 0:
                self.logger.info(f"[{quiz_log_id}] 💾 INCREMENTAL SAVE COMPLETE: {saved_count} questions saved to CSV files")
            else:
                self.logger.warning(f"[{quiz_log_id}] ⚠️ No questions were saved from this quiz")
                
            return saved_count
            
        except Exception as e:
            self.logger.error(f"[{quiz_log_id}] Error in incremental save: {e}")
            self.logger.debug(f"[{quiz_log_id}] Incremental save error details:", exc_info=True)
            return 0

    async def _optimized_page_goto(self, page: Page, url: str, timeout: int = None, force_network_wait: bool = False) -> None:
        """
        Optimized page navigation with speed profile considerations.
        
        SPEED OPTIMIZATIONS:
        ===================
        - Skip networkidle wait for faster profiles
        - Use shorter timeouts for aggressive profiles
        - Fast-fail on problematic pages
        - Parallel resource loading when possible
        - EXCEPTION: Always wait for critical pages (results pages with descriptions)
        """
        timeout = timeout or self.config['scraper']['timeouts']['page_load']
        
        try:
            # Navigate to page
            await page.goto(url, timeout=timeout)
            
            # Wait strategy based on speed profile
            if self.wait_for_networkidle or force_network_wait:
                # Conservative: wait for network to be idle
                # OR forced wait for critical pages (like results pages)
                await page.wait_for_load_state('networkidle', timeout=self.config['scraper']['timeouts']['network_idle'])
            else:
                # Fast: just wait for DOM to be ready
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                
                # For very fast profiles, add minimal wait for dynamic content
                if self.speed_profile in ['aggressive', 'turbo']:
                    await page.wait_for_timeout(500)  # Just 0.5 seconds
                else:
                    await page.wait_for_timeout(1500)  # 1.5 seconds for fast profile
                    
        except Exception as e:
            if self.auto_slowdown_on_errors:
                self.performance_stats['errors_encountered'] += 1
                # If too many errors, automatically switch to safer mode temporarily
                if self.performance_stats['errors_encountered'] > 10:
                    self.logger.warning("High error rate detected - temporarily slowing down")
                    self.wait_for_networkidle = True
            raise

    async def _fast_radio_button_interaction(self, page: Page, questions: List[Dict[str, Any]]) -> int:
        """
        Optimized radio button selection using batch processing and parallel interactions.
        
        PERFORMANCE OPTIMIZATIONS:
        =========================
        - Batch process multiple questions simultaneously
        - Use optimized selectors for faster DOM queries
        - Skip visibility checks for faster profiles
        - Parallel interaction attempts
        """
        if not self.fast_radio_button_selection:
            # Fall back to original method
            await self._submit_all_quiz_answers(page, questions)
            return len(questions)
        
        selected_count = 0
        
        try:
            # Optimized approach: Get all radio buttons at once
            all_radios = await page.query_selector_all('input[type="radio"]')
            self.logger.debug(f"Found {len(all_radios)} radio buttons for batch processing")
            
            if not all_radios:
                return 0
            
            # For aggressive profiles, use optimized but reliable selection
            if self.speed_profile in ['aggressive', 'turbo']:
                # Calculate radios per question and select first option for each
                radios_per_question = len(all_radios) // len(questions)
                if radios_per_question > 0:
                    for i in range(len(questions)):
                        try:
                            radio_index = i * radios_per_question
                            if radio_index < len(all_radios):
                                radio = all_radios[radio_index]
                                # Ensure radio is visible and enabled first
                                await radio.scroll_into_view_if_needed()
                                await radio.check()  # Use check() instead of click() for radio buttons
                                selected_count += 1
                                self.logger.debug(f"Selected radio button {radio_index} for question {i+1}")
                        except Exception as e:
                            self.logger.debug(f"Failed to select radio {radio_index} for question {i+1}: {e}")
                            continue
            else:
                # Standard optimized approach with some safety checks
                for i, question in enumerate(questions):
                    question_num = str(i + 1)
                    patterns = [f'q{question_num}', f'question{question_num}', f'q{i+1}']
                    
                    for pattern in patterns:
                        try:
                            radios = await page.query_selector_all(f'input[name="{pattern}"][type="radio"]')
                            if radios:
                                first_radio = radios[0]
                                await first_radio.scroll_into_view_if_needed()
                                await first_radio.check()  # Use check() for radio buttons
                                selected_count += 1
                                self.logger.debug(f"Selected radio for question {i+1} using pattern {pattern}")
                                break
                        except Exception as e:
                            self.logger.debug(f"Failed to select radio for question {i+1} with pattern {pattern}: {e}")
                            continue
                    
                    if selected_count <= i:  # If we didn't select this question
                        # Try positional fallback
                        try:
                            estimated_index = i * (len(all_radios) // len(questions))
                            if estimated_index < len(all_radios):
                                radio = all_radios[estimated_index]
                                await radio.scroll_into_view_if_needed()
                                await radio.check()
                                selected_count += 1
                                self.logger.debug(f"Selected radio using positional fallback for question {i+1}")
                        except Exception as e:
                            self.logger.debug(f"Positional fallback failed for question {i+1}: {e}")
                            pass
            
            self.logger.info(f"Fast radio selection: {selected_count}/{len(questions)} questions")
            return selected_count
            
        except Exception as e:
            self.logger.error(f"Fast radio button selection failed: {e}")
            # Fall back to original method
            await self._submit_all_quiz_answers(page, questions)
            return len(questions)

    async def _parallel_media_download(self, questions: List[Dict[str, Any]], quiz_log_id: str) -> List[Dict[str, Any]]:
        """
        Download media files in parallel for better performance.
        
        PARALLEL PROCESSING:
        ===================
        - Download all media files simultaneously
        - Group by media type for efficient processing
        - Handle failures gracefully without blocking other downloads
        - Update questions with downloaded media filenames
        """
        if not self.parallel_media_downloads:
            return questions  # Use original sequential method
        
        # Collect all media download tasks
        download_tasks = []
        task_to_question_map = {}
        
        for question in questions:
            # Audio downloads
            if question.get('type') == 'sound':
                audio_url = self._extract_audio_url(question)
                if audio_url:
                    task = self._download_media_async(audio_url, question.get('id'), 'audio')
                    download_tasks.append(task)
                    task_to_question_map[len(download_tasks) - 1] = (question, 'audio')
            
            # Image downloads
            elif question.get('isPhotoQuiz') or question.get('imageUrl'):
                image_url = question.get('imageUrl')
                if image_url:
                    task = self._download_media_async(image_url, question.get('id'), 'image')
                    download_tasks.append(task)
                    task_to_question_map[len(download_tasks) - 1] = (question, 'image')
        
        if download_tasks:
            self.logger.info(f"[{quiz_log_id}] Starting parallel download of {len(download_tasks)} media files")
            
            # Execute downloads in parallel
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # Process results and update questions
            successful_downloads = 0
            for i, result in enumerate(results):
                if i in task_to_question_map and not isinstance(result, Exception):
                    question, media_type = task_to_question_map[i]
                    question['media_filename'] = result
                    successful_downloads += 1
                elif isinstance(result, Exception):
                    self.logger.debug(f"[{quiz_log_id}] Media download failed: {result}")
            
            self.logger.info(f"[{quiz_log_id}] Parallel media downloads: {successful_downloads}/{len(download_tasks)} successful")
        
        return questions

    async def _download_media_async(self, url: str, question_id: str, media_type: str) -> str:
        """Async wrapper for media downloads."""
        return await self.media_handler.download_media(
            url=url,
            question_id=question_id,
            media_type=media_type,
            user_agent=self._get_random_user_agent()
        )