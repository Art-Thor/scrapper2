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

from .base import BaseScraper
from .config import ScraperConfig
from .media import MediaHandler, MediaReference
from ..utils.rate_limiter import RateLimiter
from ..utils.indexing import QuestionIndexer
from ..utils.question_classifier import QuestionClassifier
from ..utils.text_processor import TextProcessor
from ..constants import (
    TIMEOUTS, USER_AGENTS, DESCRIPTION_SELECTORS, 
    THRESHOLDS, DEFAULT_PATHS
)


class FunTriviaScraper(BaseScraper):
    """
    Enhanced FunTrivia scraper with improved question type detection,
    description extraction, and organized modular structure.
    """
    
    def __init__(self, config_path: str = None):
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

    async def initialize(self) -> None:
        """Initialize the scraper with a browser instance."""
        try:
            from playwright.async_api import async_playwright # type: ignore
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            self._ensure_directories()
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
        """Scrape questions from FunTrivia.com with comprehensive logging."""
        if not self.browser:
            await self.initialize()

        questions = []
        scraping_stats = {
            'categories_processed': 0,
            'categories_failed': 0,
            'quizzes_processed': 0,
            'quizzes_failed': 0,
            'questions_extracted': 0,
            'questions_by_type': {'multiple_choice': 0, 'true_false': 0, 'sound': 0},
            'media_downloads': {'attempted': 0, 'successful': 0, 'failed': 0},
            'mapping_issues': {'domain': set(), 'topic': set(), 'difficulty': set()}
        }
        
        try:
            self.logger.info("="*60)
            self.logger.info("STARTING FUNTIVIA SCRAPING SESSION")
            self.logger.info("="*60)
            self.logger.info(f"Target: {max_questions if max_questions else 'unlimited'} questions")
            self.logger.info(f"Configuration: {self.config['scraper']['concurrency']} concurrent browsers")
            self.logger.info(f"Delay range: {self.config['scraper']['delays']['min']}-{self.config['scraper']['delays']['max']}s")
            
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
                await page.goto(quiz_url, timeout=TIMEOUTS['quiz_page'])
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['quiz_wait'])
                self.logger.debug(f"[{quiz_log_id}] Page loaded successfully")

            # Step 2: Extract quiz metadata before starting
            quiz_metadata = await self._extract_quiz_metadata(page)
            self.logger.debug(f"[{quiz_log_id}] Extracted metadata: domain={quiz_metadata.get('domain')}, topic={quiz_metadata.get('topic')}, difficulty={quiz_metadata.get('difficulty')}")

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
                questions_with_results, {}, quiz_metadata, stats, quiz_log_id
            )
                
            if processed_questions:
                self.logger.info(f"[{quiz_log_id}] Successfully processed {len(processed_questions)} questions")
                if stats:
                    stats['questions_extracted'] += len(processed_questions)
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

    async def _process_extracted_questions(self, questions: List[Dict[str, Any]], descriptions: Dict[str, str], metadata: Dict[str, str], stats: Dict = None, quiz_log_id: str = "") -> List[Dict[str, Any]]:
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
                
                # Add description if available
                question_number = question_data.get('questionNumber', str(i+1))
                description = descriptions.get(question_number, '')
                
                # Clean and process text fields
                cleaned_question = self.text_processor.clean_question_text(question_text)
                cleaned_description = self.text_processor.clean_description_text(description)
                
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
                    "hint": question_data.get('hint', ''),
                    "description": cleaned_description,
                    "media_filename": media_filename
                })
                
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
                await page.goto(
                    f"{self.config['scraper']['base_url']}/quizzes/", 
                    timeout=TIMEOUTS['page_load']
                )
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['network_idle'])
                
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
                await page.goto(category_url, timeout=TIMEOUTS['page_load'])
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['network_idle'])
                
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
        """Get the quiz domain/category from FunTrivia's main category (first level) with logging."""
        try:
            domain = await page.evaluate("""
                () => {
                    // Strategy 1: Parse breadcrumbs for the main category
                    const breadcrumbSelectors = [
                        '.breadcrumb a, .breadcrumbs a',
                        'nav a',
                        '[itemtype*="BreadcrumbList"] a',
                        '.nav-breadcrumb a'
                    ];
                    
                    for (const selector of breadcrumbSelectors) {
                        const breadcrumbLinks = document.querySelectorAll(selector);
                        if (breadcrumbLinks.length > 1) {
                            // Skip first link (usually "Home") and get the main category
                            for (let i = 1; i < breadcrumbLinks.length; i++) {
                                const link = breadcrumbLinks[i];
                                const text = link.textContent.trim();
                                const href = link.href || '';
                                
                                // Look for main category indicators in href or text
                                if (href.includes('/Sports/') || text.toLowerCase() === 'sports') {
                                    return 'Sports';
                                } else if (href.includes('/Geography/') || text.toLowerCase() === 'geography') {
                                    return 'Geography';
                                } else if (href.includes('/History/') || text.toLowerCase() === 'history') {
                                    return 'History';
                                } else if (href.includes('/Science/') || text.toLowerCase() === 'science') {
                                    return 'Science';
                                } else if (href.includes('/Entertainment/') || 
                                          href.includes('/Music/') || 
                                          href.includes('/Movies/') || 
                                          href.includes('/Literature/') ||
                                          href.includes('/People/') ||
                                          text.toLowerCase().includes('entertainment') ||
                                          text.toLowerCase().includes('music') ||
                                          text.toLowerCase().includes('movies') ||
                                          text.toLowerCase().includes('literature') ||
                                          text.toLowerCase().includes('people')) {
                                    return 'Culture';
                                } else if (href.includes('/Animals/') || 
                                          href.includes('/Nature/') ||
                                          text.toLowerCase().includes('animals') ||
                                          text.toLowerCase().includes('nature')) {
                                    return 'Nature';
                                } else if (href.includes('/Religion/') || text.toLowerCase().includes('religion')) {
                                    return 'Religion';
                                }
                            }
                        }
                    }
                    
                    // Strategy 2: Look in URL path for main category
                    const urlPath = window.location.pathname;
                    const pathParts = urlPath.split('/').filter(part => part && 
                        part !== 'quiz' && 
                        part !== 'trivia-quiz' && 
                        part !== 'en' &&
                        !part.endsWith('.html'));
                    
                    if (pathParts.length > 0) {
                        const mainCategory = pathParts[0].toLowerCase();
                        
                        // Map URL categories to domains based on FunTrivia structure
                        const categoryMap = {
                            'sports': 'Sports',
                            'geography': 'Geography', 
                            'world': 'Geography',
                            'history': 'History',
                            'science': 'Science',
                            'entertainment': 'Culture',
                            'music': 'Culture',
                            'movies': 'Culture',
                            'literature': 'Culture',
                            'people': 'Culture',
                            'humanities': 'Culture',
                            'general': 'Culture',
                            'animals': 'Nature',
                            'nature': 'Nature',
                            'religion': 'Religion'
                        };
                        
                        if (categoryMap[mainCategory]) {
                            return categoryMap[mainCategory];
                        }
                        
                        // Return capitalized category if not specifically mapped
                        return mainCategory.charAt(0).toUpperCase() + mainCategory.slice(1);
                    }
                    
                    // Strategy 3: Look in page title for category hints
                    const title = document.title.toLowerCase();
                    if (title.includes('sports')) return 'Sports';
                    if (title.includes('geography') || title.includes('world')) return 'Geography';
                    if (title.includes('history')) return 'History';
                    if (title.includes('science')) return 'Science';
                    if (title.includes('animal') || title.includes('nature')) return 'Nature';
                    if (title.includes('religion')) return 'Religion';
                    
                    return 'Culture'; // Default for entertainment/general content
                }
            """)
            self.logger.debug(f"Detected domain: {domain}")
            return domain
        except Exception as e:
            self.logger.debug(f"Error getting domain: {e}")
            return "Culture"

    async def _get_quiz_topic(self, page: Page) -> str:
        """Get the quiz topic from FunTrivia's subcategory (second level) with logging."""
        try:
            topic = await page.evaluate("""
                () => {
                    // Strategy 1: Parse breadcrumbs for the subcategory
                    const breadcrumbSelectors = [
                        '.breadcrumb a, .breadcrumbs a',
                        'nav a',
                        '[itemtype*="BreadcrumbList"] a',
                        '.nav-breadcrumb a'
                    ];
                    
                    for (const selector of breadcrumbSelectors) {
                        const breadcrumbLinks = document.querySelectorAll(selector);
                        if (breadcrumbLinks.length > 2) {
                            // Get the subcategory (second level after main category)
                            // Structure: Home » MainCategory » SubCategory » Quiz
                            for (let i = 2; i < breadcrumbLinks.length - 1; i++) {
                                const link = breadcrumbLinks[i];
                                const text = link.textContent.trim();
                                
                                // Clean up the subcategory name
                                if (text && text.length > 2 && text.length < 50) {
                                    // Remove common suffixes and clean
                                    let cleanTopic = text
                                        .replace(/\s*(trivia|quiz|quizzes)\s*$/i, '')
                                        .replace(/\s+/g, ' ')
                                        .trim();
                                    
                                    if (cleanTopic && cleanTopic.length > 2) {
                                        return cleanTopic;
                                    }
                                }
                            }
                        }
                    }
                    
                    // Strategy 2: Extract from URL path (second level)
                    const urlPath = window.location.pathname;
                    const pathParts = urlPath.split('/').filter(part => part && 
                        part !== 'quiz' && 
                        part !== 'trivia-quiz' && 
                        part !== 'en' &&
                        !part.endsWith('.html'));
                    
                    if (pathParts.length > 1) {
                        const subCategory = pathParts[1];
                        
                        // Clean up subcategory from URL
                        let cleanTopic = subCategory
                            .replace(/[-_]/g, ' ')  // Replace hyphens and underscores with spaces
                            .replace(/([a-z])([A-Z])/g, '$1 $2')  // Add space before capital letters
                            .split(' ')
                            .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
                            .join(' ')
                            .trim();
                        
                        if (cleanTopic && cleanTopic.length > 2) {
                            return cleanTopic;
                        }
                    }
                    
                    // Strategy 3: Look in page content for category information
                    const categoryInfo = document.querySelector('.category-info, .quiz-category, .topic-header');
                    if (categoryInfo) {
                        const text = categoryInfo.textContent.trim();
                        const topicMatch = text.match(/(?:category|topic):\s*([^\n\r]{3,40})/i);
                        if (topicMatch) {
                            return topicMatch[1].trim();
                        }
                    }
                    
                    // Strategy 4: Extract from quiz description or metadata
                    const descriptionSelectors = [
                        '.quiz-description',
                        '.category-description', 
                        'meta[name="description"]',
                        '.topic-intro'
                    ];
                    
                    for (const selector of descriptionSelectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            const content = element.content || element.textContent;
                            if (content) {
                                // Look for patterns like "related to X" or "about X"
                                const topicMatch = content.match(/(?:related to|about|concerning)\s+([A-Z][^.]{2,30})/i);
                                if (topicMatch) {
                                    return topicMatch[1].trim();
                                }
                            }
                        }
                    }
                    
                    // Strategy 5: Last resort - clean up h1 title but only if it looks like a category name
                    const titleElement = document.querySelector('h1');
                    if (titleElement) {
                        let title = titleElement.textContent.trim();
                        title = title.replace(/\s*(trivia\s*)?(questions?\s*and\s*answers?|quiz)\s*$/i, '').trim();
                        
                        // Only use if it looks like a category name (not too specific)
                        if (title.length > 3 && title.length < 30 && 
                            !title.match(/\d/) && // No numbers
                            !title.includes('?') && // No question marks
                            !title.toLowerCase().includes('trivia') && // Not generic "trivia"
                            !title.toLowerCase().includes('questions') && // Not generic "questions"
                            title.split(' ').length <= 4) { // Not too many words
                            return title;
                        }
                    }
                    
                    return 'General';
                }
            """)
            self.logger.debug(f"Detected topic: {topic}")
            return topic
        except Exception as e:
            self.logger.debug(f"Error getting topic: {e}")
            return "General"

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
            await self._submit_all_quiz_answers(page, questions)
            
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
        """
        selected_count = 0
        
        try:
            for i, question in enumerate(questions):
                question_num = question.get('questionNumber', str(i+1))
                
                # Try multiple naming patterns for radio buttons
                name_patterns = [
                    f'q{question_num}',
                    f'question{question_num}', 
                    f'q{i+1}',
                    f'question{i+1}',
                    f'answer{question_num}',
                    f'ans{question_num}'
                ]
                
                answer_selected = False
                for name_pattern in name_patterns:
                    try:
                        radios = await page.query_selector_all(f'input[name="{name_pattern}"][type="radio"]')
                        if radios and len(radios) > 0:
                            # Always select the first option
                            await radios[0].click()
                            selected_count += 1
                            answer_selected = True
                            self.logger.debug(f"Selected first option for question {question_num} (pattern: {name_pattern})")
                            break
                    except Exception as e:
                        self.logger.debug(f"Failed to select answer with pattern {name_pattern}: {e}")
                        continue
                
                if not answer_selected:
                    self.logger.warning(f"Could not select answer for question {question_num}")
            
            self.logger.info(f"Successfully selected answers for {selected_count}/{len(questions)} questions")
            
            if selected_count == 0:
                raise Exception("No radio buttons found - cannot submit quiz")
                
        except Exception as e:
            self.logger.error(f"Error submitting quiz answers: {e}")
            raise

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
        """
        try:
            # Strategy 1: Wait for network idle (most reliable)
            try:
                await page.wait_for_load_state('networkidle', timeout=60000)
                self.logger.debug("Results page loaded - network idle detected")
            except Exception:
                self.logger.debug("Network idle timeout - trying alternative detection")
            
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
        """
        try:
            self.logger.info("Starting comprehensive results extraction from results page")
            
            # Strategy 1: Look for structured result blocks
            enhanced_questions = await self._extract_from_result_blocks(page, original_questions)
            if enhanced_questions:
                return enhanced_questions
            
            # Strategy 2: Parse results from text-based format (fallback)
            enhanced_questions = await self._extract_from_text_results(page, original_questions)
            if enhanced_questions:
                return enhanced_questions
            
            # Strategy 3: Last resort - use original questions with minimal enhancement
            return await self._enhance_questions_basic(original_questions)
            
        except Exception as e:
            self.logger.error(f"Error in comprehensive results extraction: {e}")
            return await self._enhance_questions_basic(original_questions)

    async def _extract_from_result_blocks(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract results from structured result blocks."""
        try:
            result_selectors = ['.questionReview', '.questionTable', '.result-item', '.question-result']
            result_blocks = []
            
            for selector in result_selectors:
                result_blocks = await page.query_selector_all(selector)
                if result_blocks and len(result_blocks) >= len(original_questions):
                    break
            
            if not result_blocks:
                return []
            
            enhanced_questions = []
            for i, (question, result_block) in enumerate(zip(original_questions, result_blocks)):
                try:
                    # Extract correct answer and hint from result block
                    correct_answer = await self._extract_correct_answer_from_block(result_block)
                    hint = await self._extract_hint_from_block(result_block)
                    
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = correct_answer or question.get('options', [''])[0]
                    enhanced_question['hint'] = hint or ''
                    
                    enhanced_questions.append(enhanced_question)
                    
                except Exception as e:
                    self.logger.debug(f"Error processing result block {i}: {e}")
                    enhanced_questions.append(question)
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.debug(f"Error extracting from result blocks: {e}")
            return []

    async def _extract_from_text_results(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract results from text-based results format."""
        try:
            page_text = await page.evaluate('document.body.innerText')
            lines = page_text.split('\n')
            enhanced_questions = []
            
            for i, question in enumerate(original_questions):
                enhanced_question = question.copy()
                enhanced_question['correct_answer'] = question.get('options', [''])[0]
                enhanced_question['hint'] = ''
                enhanced_questions.append(enhanced_question)
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.debug(f"Error extracting from text results: {e}")
            return []

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

    async def _extract_hint_from_block(self, result_block) -> Optional[str]:
        """Extract hint/explanation from a result block."""
        try:
            text = await result_block.inner_text()
            patterns = [
                r'Explanation:\s*(.+?)(?:\n\n|$)',
                r'Hint:\s*(.+?)(?:\n\n|$)',
                r'Info:\s*(.+?)(?:\n\n|$)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    return match.group(1).strip()
                    
        except Exception as e:
            self.logger.debug(f"Error extracting hint: {e}")
        return None

    async def _enhance_questions_basic(self, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Basic enhancement of questions when results page extraction fails."""
        enhanced_questions = []
        
        for question in original_questions:
            enhanced_question = question.copy()
            enhanced_question['correct_answer'] = question.get('options', ['Unknown'])[0]
            enhanced_question['hint'] = ''
            enhanced_questions.append(enhanced_question)
        
        return enhanced_questions

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
        """
        Get statistics about the loaded mappings.
        
        Returns:
            Dictionary with counts and statistics for each mapping type
        """
        return self.scraper_config.get_mapping_stats()

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