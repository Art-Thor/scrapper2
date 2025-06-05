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
        """
        Extract quiz domain by parsing breadcrumb navigation and mapping to internal domain list.
        
        Parses the breadcrumb navigation to find the second-to-last element (main category)
        and maps it to our internal domain list: Nature, Science, Geography, Culture, Sports, History.
        
        Expected breadcrumb structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
        The [MainCategory] is mapped to our internal domain.
        """
        try:
            # Extract breadcrumb information from the page
            breadcrumb_info = await page.evaluate("""
                () => {
                    // Strategy 1: Look for breadcrumb navigation elements
                    const breadcrumbSelectors = [
                        '.breadcrumb a, .breadcrumbs a',
                        'nav a, nav li a',
                        '[itemtype*="BreadcrumbList"] a',
                        '.nav-breadcrumb a',
                        '.crumb a, .crumbs a',
                        'ol.breadcrumb a, ul.breadcrumb a'
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
                            'nav',
                            '.nav-breadcrumb',
                            '.crumb, .crumbs'
                        ];
                        
                        for (const selector of breadcrumbTextSelectors) {
                            const element = document.querySelector(selector);
                            if (element) {
                                const text = element.textContent;
                                // Look for typical breadcrumb separators
                                const separators = ['»', '>', '/', '\\', '|', '::'];
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
                    
                    return {
                        breadcrumbs: breadcrumbElements,
                        url: window.location.pathname,
                        title: document.title
                    };
                }
            """)
            
            raw_domain = None
            
            # Extract domain from breadcrumbs (second-to-last element)
            if breadcrumb_info['breadcrumbs'] and len(breadcrumb_info['breadcrumbs']) > 2:
                # Skip first element (usually "Home") and get the main category
                # Structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
                # We want the second-to-last meaningful element
                meaningful_breadcrumbs = [
                    b for b in breadcrumb_info['breadcrumbs'] 
                    if b['text'].lower() not in ['home', 'quizzes', 'trivia', 'quiz']
                ]
                
                if len(meaningful_breadcrumbs) >= 2:
                    # Get the second-to-last element as domain
                    raw_domain = meaningful_breadcrumbs[-2]['text'].strip()
                elif len(meaningful_breadcrumbs) >= 1:
                    # Fallback to first meaningful element
                    raw_domain = meaningful_breadcrumbs[0]['text'].strip()
            
            # Fallback: Extract from URL if breadcrumbs parsing failed
            if not raw_domain:
                url_path = breadcrumb_info['url']
                path_parts = [p for p in url_path.split('/') if p and p not in ['quiz', 'trivia-quiz', 'en']]
                if path_parts:
                    raw_domain = path_parts[0].replace('-', ' ').replace('_', ' ').title()
            
            # Final fallback: Extract from page title
            if not raw_domain:
                title = breadcrumb_info['title']
                title_parts = title.split(' - ')
                if len(title_parts) > 1:
                    raw_domain = title_parts[0].strip()
                else:
                    raw_domain = "Entertainment"  # Common default for FunTrivia
            
            self.logger.debug(f"Raw domain extracted from breadcrumbs: '{raw_domain}'")
            
            # Map the raw domain to our internal domain list using the configuration
            if raw_domain:
                mapped_domain = self.scraper_config.map_domain(raw_domain)
                self.logger.debug(f"Domain mapping: '{raw_domain}' -> '{mapped_domain}'")
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
        
        Parses the breadcrumb navigation to find the last meaningful element (subcategory)
        and maps it to our internal topic list using the topic mapping configuration.
        
        Expected breadcrumb structure: Home » Quizzes » [MainCategory] » [SubCategory] » Quiz
        The [SubCategory] is mapped to our internal topic, with fallback to raw string if not found.
        """
        try:
            # Extract breadcrumb information from the page
            breadcrumb_info = await page.evaluate("""
                () => {
                    // Strategy 1: Look for breadcrumb navigation elements
                    const breadcrumbSelectors = [
                        '.breadcrumb a, .breadcrumbs a',
                        'nav a, nav li a',
                        '[itemtype*="BreadcrumbList"] a',
                        '.nav-breadcrumb a',
                        '.crumb a, .crumbs a',
                        'ol.breadcrumb a, ul.breadcrumb a'
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
                            'nav',
                            '.nav-breadcrumb',
                            '.crumb, .crumbs'
                        ];
                        
                        for (const selector of breadcrumbTextSelectors) {
                            const element = document.querySelector(selector);
                            if (element) {
                                const text = element.textContent;
                                // Look for typical breadcrumb separators
                                const separators = ['»', '>', '/', '\\', '|', '::'];
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
                    
                    return {
                        breadcrumbs: breadcrumbElements,
                        url: window.location.pathname,
                        title: document.title
                    };
                }
            """)
            
            raw_topic = None
            
            # Extract topic from breadcrumbs (last meaningful element)
            if breadcrumb_info['breadcrumbs'] and len(breadcrumb_info['breadcrumbs']) > 1:
                # Filter out non-meaningful breadcrumb elements
                meaningful_breadcrumbs = [
                    b for b in breadcrumb_info['breadcrumbs'] 
                    if b['text'].lower() not in ['home', 'quizzes', 'trivia', 'quiz']
                ]
                
                if len(meaningful_breadcrumbs) >= 1:
                    # Get the last meaningful element as topic (subcategory)
                    raw_topic = meaningful_breadcrumbs[-1]['text'].strip()
                    
                    # Clean up the topic by removing common suffixes
                    raw_topic = raw_topic.replace(' Trivia', '').replace(' Quiz', '').replace(' Quizzes', '').strip()
            
            # Fallback: Extract from URL if breadcrumbs parsing failed
            if not raw_topic:
                url_path = breadcrumb_info['url']
                path_parts = [p for p in url_path.split('/') if p and p not in ['quiz', 'trivia-quiz', 'en']]
                if len(path_parts) > 1:
                    raw_topic = path_parts[-1].replace('-', ' ').replace('_', ' ').title()
                elif len(path_parts) > 0:
                    raw_topic = path_parts[0].replace('-', ' ').replace('_', ' ').title()
            
            # Final fallback: Extract from page title
            if not raw_topic:
                title = breadcrumb_info['title']
                # Try to extract topic from title pattern
                title_lower = title.lower()
                if 'trivia' in title_lower:
                    # Extract the part before 'trivia'
                    parts = title.split(' Trivia')[0].split(' - ')
                    if parts:
                        raw_topic = parts[-1].strip()
                else:
                    title_parts = title.split(' - ')
                    if len(title_parts) > 1:
                        raw_topic = title_parts[-1].strip()
                    else:
                        raw_topic = "General"
            
            self.logger.debug(f"Raw topic extracted from breadcrumbs: '{raw_topic}'")
            
            # Map the raw topic to our internal topic list using the configuration
            if raw_topic:
                mapped_topic = self.scraper_config.map_topic(raw_topic)
                self.logger.debug(f"Topic mapping: '{raw_topic}' -> '{mapped_topic}'")
                
                # Log warning if mapping failed (fallback to raw value)
                if mapped_topic == raw_topic:
                    # Check if this is actually a failed mapping (not in our config)
                    topic_found_in_config = False
                    for std_topic, raw_values in self.scraper_config.mappings['topic_mapping'].items():
                        if raw_topic.lower() in [v.lower() for v in raw_values]:
                            topic_found_in_config = True
                            break
                    
                    if not topic_found_in_config:
                        self.logger.warning(f"Topic '{raw_topic}' not found in topic mapping config. Using raw value as fallback. Consider adding to topic_mapping in mappings.json")
                
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
        """
        Extract results from structured result blocks on the results page.
        
        This method locates individual result blocks for each question and extracts:
        - Correct answer information
        - Full explanation/description blocks ("Interesting Information")
        - Handles both single and multi-paragraph explanations
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
                '.question-block'            # Question block wrapper
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
        
        Looks for explanation blocks that follow question results, including:
        - "Interesting Information:" sections
        - "Explanation:" blocks
        - Multi-paragraph descriptions following the correct answer
        """
        try:
            explanation_parts = []
            in_explanation = False
            explanation_started = False
            
            for i, line in enumerate(lines):
                line_lower = line.lower()
                
                # Check if we're at the right question
                if f"question {question_num}" in line_lower or (f"{question_num}." in line and len(line) < 50):
                    explanation_started = True
                    continue
                
                if not explanation_started:
                    continue
                
                # Look for explanation start markers
                explanation_markers = [
                    'interesting information',
                    'interesting info',
                    'explanation',
                    'additional information',
                    'trivia',
                    'did you know',
                    'fun fact',
                    'background',
                    'more info'
                ]
                
                if any(marker in line_lower for marker in explanation_markers):
                    in_explanation = True
                    # If the line contains both marker and text, include the text part
                    for marker in explanation_markers:
                        if marker in line_lower:
                            marker_end = line_lower.index(marker) + len(marker)
                            text_after_marker = line[marker_end:].strip(' :')
                            if text_after_marker:
                                explanation_parts.append(text_after_marker)
                            break
                    continue
                
                # If we're in an explanation, collect lines until we hit a stopping condition
                if in_explanation:
                    # Stop conditions for explanation
                    stop_conditions = [
                        line_lower.startswith('question'),  # Next question
                        'your score' in line_lower,         # Score section
                        'quiz complete' in line_lower,      # Quiz end
                        line_lower.startswith('correct answer:'),  # Another question's answer
                        len(line) < 10 and line.isdigit(),  # Question number alone
                        'submit' in line_lower and 'quiz' in line_lower  # Submit buttons
                    ]
                    
                    if any(condition for condition in stop_conditions):
                        break
                    
                    # Collect meaningful explanation text
                    if (len(line) > 15 and  # Substantial content
                        not line.lower().startswith(('a)', 'b)', 'c)', 'd)')) and  # Not answer options
                        not line.lower().startswith('question') and  # Not question text
                        'correct answer' not in line_lower):  # Not answer declaration
                        
                        explanation_parts.append(line)
                
                # Check if we've moved to the next question (stop collecting)
                next_question_num = str(int(question_num) + 1)
                if (f"question {next_question_num}" in line_lower or 
                    (f"{next_question_num}." in line and len(line) < 50)):
                    break
            
            # Join explanation parts with proper spacing
            if explanation_parts:
                explanation = ' '.join(explanation_parts).strip()
                # Clean up extra whitespace
                explanation = ' '.join(explanation.split())
                return explanation if len(explanation) > 20 else None  # Minimum length filter
            
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
        Extract explanation/description from a result block element.
        
        This method handles various layouts of result blocks and looks for:
        1. "Interesting Information" sections (FunTrivia's standard explanation label)
        2. Generic explanation markers like "Explanation:", "Info:", etc.
        3. Multi-paragraph explanation blocks
        4. Explanations that may contain embedded media or special formatting
        
        Args:
            result_block: The DOM element containing the question's results
            question_num: Question number for logging purposes
            
        Returns:
            Extracted explanation text or None if not found
        """
        try:
            # Get all text content from the result block
            block_text = await result_block.inner_text()
            
            if not block_text:
                return None
            
            # Strategy 1: Look for "Interesting Information" sections (FunTrivia standard)
            explanation = self._extract_interesting_information(block_text)
            if explanation:
                self.logger.debug(f"Found 'Interesting Information' for Q{question_num}")
                return explanation
            
            # Strategy 2: Look for other explanation markers
            explanation = self._extract_generic_explanation(block_text)
            if explanation:
                self.logger.debug(f"Found generic explanation for Q{question_num}")
                return explanation
            
            # Strategy 3: Look for explanation in HTML structure
            explanation = await self._extract_explanation_from_html_structure(result_block)
            if explanation:
                self.logger.debug(f"Found structured explanation for Q{question_num}")
                return explanation
            
            # Strategy 4: Heuristic-based extraction (look for substantial text blocks)
            explanation = self._extract_heuristic_explanation(block_text)
            if explanation:
                self.logger.debug(f"Found heuristic explanation for Q{question_num}")
                return explanation
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting explanation from block for Q{question_num}: {e}")
            return None

    def _extract_interesting_information(self, text: str) -> Optional[str]:
        """
        Extract text from "Interesting Information" sections.
        
        FunTrivia commonly uses "Interesting Information:" as the label for
        question explanations. This method finds and extracts that content.
        """
        try:
            # Look for "Interesting Information" patterns (case insensitive)
            patterns = [
                r'Interesting Information:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Interesting Info:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Interesting Information\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'(?:^|\n)Interesting Information[:\s]*\n(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    explanation = match.group(1).strip()
                    # Clean up the explanation text
                    explanation = self._clean_explanation_text(explanation)
                    if len(explanation) > 20:  # Minimum meaningful length
                        return explanation
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting interesting information: {e}")
            return None

    def _extract_generic_explanation(self, text: str) -> Optional[str]:
        """
        Extract explanations using generic markers like "Explanation:", "Info:", etc.
        """
        try:
            # Generic explanation patterns
            patterns = [
                r'Explanation:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Info:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Additional Information:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Details:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Trivia:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Did you know[?:]\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Fun fact[?:]\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))',
                r'Background:\s*(.+?)(?:\n\n|\n(?=Question|\d+\.|\Z))'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    explanation = match.group(1).strip()
                    explanation = self._clean_explanation_text(explanation)
                    if len(explanation) > 20:
                        return explanation
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error extracting generic explanation: {e}")
            return None

    async def _extract_explanation_from_html_structure(self, result_block) -> Optional[str]:
        """
        Extract explanation by analyzing the HTML structure of the result block.
        
        Looks for specific elements that commonly contain explanations:
        - Divs or paragraphs with explanation-related classes
        - Text that follows the correct answer in the DOM structure
        """
        try:
            # Look for explanation-specific elements
            explanation_selectors = [
                '.explanation',
                '.interesting-info',
                '.additional-info',
                '.trivia-info',
                '.fun-fact',
                '.background-info',
                'p:has-text("Interesting")',
                'div:has-text("Interesting")',
                '[class*="explanation"]',
                '[class*="interesting"]',
                '[class*="info"]'
            ]
            
            for selector in explanation_selectors:
                try:
                    explanation_element = await result_block.query_selector(selector)
                    if explanation_element:
                        text = await explanation_element.inner_text()
                        if text and len(text) > 20:
                            return self._clean_explanation_text(text)
                except Exception:
                    continue
            
            # Fallback: Look for substantial text blocks after "Correct Answer"
            try:
                all_elements = await result_block.query_selector_all('p, div')
                found_correct_answer = False
                
                for element in all_elements:
                    element_text = await element.inner_text()
                    element_text_lower = element_text.lower()
                    
                    # Mark when we pass the correct answer
                    if 'correct answer' in element_text_lower:
                        found_correct_answer = True
                        continue
                    
                    # Look for substantial explanation text after correct answer
                    if (found_correct_answer and 
                        len(element_text) > 30 and 
                        not element_text_lower.startswith(('question', 'q.', 'your score'))):
                        
                        cleaned_text = self._clean_explanation_text(element_text)
                        if len(cleaned_text) > 20:
                            return cleaned_text
                
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
            
            explanation_candidates = []
            found_correct_answer = False
            
            for line in lines:
                line_lower = line.lower()
                
                # Mark when we pass the correct answer line
                if 'correct answer' in line_lower:
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
        Clean and normalize explanation text.
        
        Removes excessive whitespace, cleans up formatting artifacts,
        and normalizes the text for storage in the CSV output.
        """
        if not text:
            return ""
        
        # Remove excessive whitespace and normalize line breaks
        text = ' '.join(text.split())
        
        # Remove common formatting artifacts
        text = text.replace('  ', ' ')
        text = text.strip(' .,;:')
        
        # Remove leading markers if they somehow got included
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
            'Background:'
        ]
        
        for prefix in prefixes_to_remove:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        
        return text.strip()

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