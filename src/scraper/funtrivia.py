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
from ..utils.rate_limiter import RateLimiter
from ..utils.indexing import QuestionIndexer
from ..utils.question_classifier import QuestionClassifier
from ..utils.text_processor import TextProcessor
from ..constants import (
    TIMEOUTS, RATE_LIMITS, USER_AGENTS, DESCRIPTION_SELECTORS, 
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
        
        # Initialize components
        self.mappings = self._load_mappings()
        self.indexer = QuestionIndexer()
        self.rate_limiter = RateLimiter(
            self.config['scraper']['rate_limit']['requests_per_minute']
        )
        self.question_classifier = QuestionClassifier()
        self.text_processor = TextProcessor()
        
        # Configuration
        self.strict_mapping = self.config.get('scraper', {}).get('strict_mapping', False)

    def _load_mappings(self) -> Dict[str, Any]:
        """Load mappings from JSON file."""
        try:
            mappings_path = DEFAULT_PATHS['mappings_file']
            with open(mappings_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load mappings: {e}")
            raise

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
        """Scrape questions from FunTrivia.com."""
        if not self.browser:
            await self.initialize()

        questions = []
        try:
            categories = await self._get_categories()
            self.logger.info(f"Found {len(categories)} categories")
            
            # Process categories concurrently
            questions = await self._process_categories_concurrently(categories, max_questions)
            
            self.logger.info(f"Successfully scraped {len(questions)} questions")
            return questions
        except Exception as e:
            self.logger.error(f"Error during question scraping: {e}")
            raise

    async def _process_categories_concurrently(self, categories: List[str], max_questions: Optional[int]) -> List[Dict[str, Any]]:
        """Process categories concurrently with proper semaphore control."""
        questions = []
        semaphore = asyncio.Semaphore(self.config['scraper']['concurrency'])
        
        async def scrape_category(category: str) -> List[Dict[str, Any]]:
            async with semaphore:
                try:
                    quiz_links = await self._get_quiz_links(category)
                    self.logger.info(f"Found {len(quiz_links)} quizzes in category {category}")
                    
                    category_questions = []
                    for quiz_link in quiz_links:
                        if max_questions and len(questions) >= max_questions:
                            break
                        
                        async with self.rate_limiter:
                            quiz_questions = await self._scrape_quiz(quiz_link)
                            category_questions.extend(quiz_questions)
                            await self._random_delay()
                    
                    return category_questions
                except Exception as e:
                    self.logger.error(f"Error scraping category {category}: {e}")
                    return []

        # Execute concurrent scraping
        tasks = [scrape_category(category) for category in categories]
        results = await asyncio.gather(*tasks)
        
        # Flatten results
        for category_questions in results:
            questions.extend(category_questions)
            if max_questions and len(questions) >= max_questions:
                questions = questions[:max_questions]
                break

        return questions

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((PlaywrightTimeoutError, Exception))
    )
    async def _get_categories(self) -> List[str]:
        """Get all category URLs from the main page."""
        context = await self.browser.new_context(
            user_agent=self._get_random_user_agent()
        )
        page = await context.new_page()
        
        try:
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
                return list(set(categories))  # Remove duplicates
        except PlaywrightTimeoutError:
            self.logger.error("Timeout while loading categories page")
            raise
        except Exception as e:
            self.logger.error(f"Error getting categories: {e}")
            raise
        finally:
            await context.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((PlaywrightTimeoutError, Exception))
    )
    async def _get_quiz_links(self, category_url: str) -> List[str]:
        """Get all quiz links from a category page."""
        context = await self.browser.new_context(
            user_agent=self._get_random_user_agent()
        )
        page = await context.new_page()
        
        try:
            async with self.rate_limiter:
                await page.goto(category_url, timeout=TIMEOUTS['page_load'])
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['network_idle'])
                
                quiz_links = await page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a[href*="/quiz/"]'));
                        return links.map(link => link.href);
                    }
                """)
                return list(set(quiz_links))  # Remove duplicates
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout while loading category page: {category_url}")
            raise
        except Exception as e:
            self.logger.error(f"Error getting quiz links for {category_url}: {e}")
            raise
        finally:
            await context.close()

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((PlaywrightTimeoutError,))
    )
    async def _scrape_quiz(self, quiz_url: str) -> List[Dict[str, Any]]:
        """Robustly scrape all questions, options, correct answers, and hints from a FunTrivia quiz."""
        context = await self.browser.new_context(user_agent=self._get_random_user_agent())
        page = await context.new_page()
        
        try:
            async with self.rate_limiter:
                await page.goto(quiz_url, timeout=TIMEOUTS['quiz_page'])
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['quiz_wait'])
                self.logger.info(f"Navigated to quiz: {quiz_url}")

                # Extract quiz metadata first (before starting quiz)
                quiz_metadata = await self._extract_quiz_metadata(page)
                self.logger.debug(f"Quiz metadata: {quiz_metadata}")

                # Check quiz type - only process Multiple Choice and Photo Quiz
                quiz_type = await self._detect_quiz_type(page)
                self.logger.info(f"Detected quiz type: {quiz_type}")
                
                if quiz_type not in ['Multiple Choice', 'Photo Quiz']:
                    self.logger.info(f"Skipping {quiz_type} - not compatible with multiple choice format")
                    return []

                # 1. Click "Start Quiz" button if present
                try:
                    start_btn = await page.query_selector('input[type="submit"][value*="Start"], input[value*="Take Quiz"], button:has-text("Start")')
                    if start_btn:
                        await start_btn.click()
                        self.logger.info("Clicked Start Quiz button")
                        await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['quiz_wait'])
                    else:
                        self.logger.info("No Start Quiz button found, proceeding to extract questions")
                except Exception as e:
                    self.logger.warning(f"Error with Start Quiz button: {e}")

                # 2. Wait for quiz form to load with robust selectors
                try:
                    await page.wait_for_selector('form[action*="score.cfm"], form[method="post"]', timeout=TIMEOUTS['quiz_page'])
                except Exception:
                    self.logger.warning("Quiz form not found with primary selectors, trying alternatives")

                # 3. Extract questions and options with robust selectors and fallbacks
                if quiz_type == 'Photo Quiz':
                    questions = await self._extract_photo_quiz_questions(page)
                else:
                    questions = await self._extract_questions_robust(page)
                
                if not questions:
                    self.logger.warning(f"No questions found on quiz page: {quiz_url}")
                    return []

                self.logger.info(f"Extracted {len(questions)} questions from quiz page")

                # 4. Submit answers to get results page
                results_with_answers = await self._submit_quiz_and_get_results(page, questions)
                
                if not results_with_answers:
                    self.logger.warning("Failed to get results from quiz submission")
                    # Fallback: use questions without correct answers
                    results_with_answers = questions

                # 5. Process questions through existing pipeline for proper formatting/mapping
                processed_questions = await self._process_extracted_questions(
                    results_with_answers, {}, quiz_metadata  # Empty descriptions dict for now
                )
                
                self.logger.info(f"Successfully processed {len(processed_questions)} questions from {quiz_url}")
                return processed_questions
                
        except Exception as e:
            self.logger.error(f"Error scraping quiz {quiz_url}: {e}")
            return []
        finally:
            await context.close()

    async def _detect_quiz_type(self, page: Page) -> str:
        """Detect the type of quiz from the page content."""
        try:
            quiz_type = await page.evaluate("""
                () => {
                    // Strategy 1: Look for quiz type in page text/headings
                    const pageText = document.body.innerText.toLowerCase();
                    
                    // Check for explicit quiz type mentions
                    if (pageText.includes('photo quiz')) return 'Photo Quiz';
                    if (pageText.includes('match quiz')) return 'Match Quiz';
                    if (pageText.includes('ordering quiz')) return 'Ordering Quiz';
                    if (pageText.includes('label quiz')) return 'Label Quiz';
                    if (pageText.includes('classification quiz')) return 'Classification Quiz';
                    if (pageText.includes('multiple choice')) return 'Multiple Choice';
                    
                    // Strategy 2: Look for images in question areas (indicates Photo Quiz)
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
                    
                    // Strategy 3: Look for specific UI patterns
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
                    
                    // Strategy 4: Default to Multiple Choice if we find radio buttons
                    const radioInputs = document.querySelectorAll('input[type="radio"]');
                    if (radioInputs.length > 0) {
                        return 'Multiple Choice';
                    }
                    
                    // Strategy 5: Look at URL patterns
                    const url = window.location.href;
                    if (url.includes('photo')) return 'Photo Quiz';
                    if (url.includes('match')) return 'Match Quiz';
                    if (url.includes('order')) return 'Ordering Quiz';
                    
                    return 'Multiple Choice'; // Default fallback
                }
            """)
            
            return quiz_type
            
        except Exception as e:
            self.logger.debug(f"Error detecting quiz type: {e}")
            return "Multiple Choice"  # Default fallback

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
            
            # Download images for photo quiz questions
            for question in questions:
                if question.get('imageUrl'):
                    question_id = f"temp_{question['questionNumber']}"
                    local_image_path = await self.download_media(
                        question['imageUrl'], 
                        'image', 
                        question_id
                    )
                    question['image_path'] = local_image_path
                    self.logger.info(f"Downloaded image for question {question['questionNumber']}")
            
            self.logger.info(f"Extracted {len(questions)} photo quiz questions")
            return questions
            
        except Exception as e:
            self.logger.error(f"Error extracting photo quiz questions: {e}")
            return []

    async def _extract_questions_robust(self, page: Page) -> List[Dict[str, Any]]:
        """Extract questions using multiple robust strategies with better validation."""
        questions = []
        
        # Strategy 1: Look for .questionBlock (newer FunTrivia format)
        try:
            question_blocks = await page.query_selector_all('.questionBlock')
            if question_blocks:
                self.logger.debug(f"Found {len(question_blocks)} .questionBlock elements")
                for i, block in enumerate(question_blocks):
                    question_data = await self._extract_question_from_block(block, i+1)
                    if question_data and self._validate_question_data(question_data):
                        questions.append(question_data)
                    elif question_data:
                        self.logger.debug(f"Question {i+1} failed validation: {question_data.get('question', '')[:50]}")
                if questions:
                    self.logger.info(f"Strategy 1 (.questionBlock) succeeded with {len(questions)} questions")
                    return questions
            else:
                self.logger.debug("No .questionBlock elements found")
        except Exception as e:
            self.logger.debug(f"Strategy 1 (.questionBlock) failed: {e}")

        # Strategy 2: Look for forms with radio input groups (most reliable for FunTrivia)
        try:
            # Find all radio inputs and group by name attribute
            radio_inputs = await page.query_selector_all('input[type="radio"]')
            self.logger.debug(f"Found {len(radio_inputs)} radio inputs total")
            
            if radio_inputs:
                question_groups = {}
                for radio in radio_inputs:
                    name = await radio.get_attribute('name')
                    if name and (name.startswith('q') or 'question' in name.lower()):
                        if name not in question_groups:
                            question_groups[name] = []
                        question_groups[name].append(radio)
                
                if question_groups:
                    self.logger.debug(f"Found {len(question_groups)} radio input groups: {list(question_groups.keys())}")
                    for i, (name, radios) in enumerate(question_groups.items(), 1):
                        question_data = await self._extract_question_from_radio_group_improved(page, name, radios, i)
                        if question_data and self._validate_question_data(question_data):
                            questions.append(question_data)
                        elif question_data:
                            self.logger.debug(f"Question {i} from radio group '{name}' failed validation: {question_data.get('question', '')[:50]}")
                    if questions:
                        self.logger.info(f"Strategy 2 (radio groups) succeeded with {len(questions)} questions")
                        return questions
                else:
                    self.logger.debug("No valid radio input groups found (no q* or question* names)")
            else:
                self.logger.debug("No radio inputs found on page")
        except Exception as e:
            self.logger.debug(f"Strategy 2 (radio groups) failed: {e}")

        # Strategy 3: Look for numbered questions in the page structure
        try:
            # Look for questions with specific numbering patterns
            question_elements = await page.query_selector_all('b, strong, .question, .quiz-question')
            self.logger.debug(f"Found {len(question_elements)} potential question elements")
            
            valid_questions = []
            
            for element in question_elements:
                text = await element.inner_text()
                # Check if this looks like a question (starts with number and has question mark or is substantial)
                if (re.match(r'^\d+\.\s+.{10,}', text.strip()) and 
                    (text.count('?') > 0 or len(text.strip()) > 20)):
                    valid_questions.append(element)
            
            if valid_questions:
                self.logger.debug(f"Found {len(valid_questions)} potential numbered question elements")
                for i, qel in enumerate(valid_questions):
                    question_data = await self._extract_question_from_numbered_element_improved(page, qel, i+1)
                    if question_data and self._validate_question_data(question_data):
                        questions.append(question_data)
                    elif question_data:
                        self.logger.debug(f"Numbered question {i+1} failed validation: {question_data.get('question', '')[:50]}")
                if questions:
                    self.logger.info(f"Strategy 3 (numbered elements) succeeded with {len(questions)} questions")
                    return questions
            else:
                self.logger.debug("No valid numbered questions found")
        except Exception as e:
            self.logger.debug(f"Strategy 3 (numbered elements) failed: {e}")

        self.logger.warning("All question extraction strategies failed")
        return questions

    def _validate_question_data(self, question_data: Dict[str, Any]) -> bool:
        """Validate that extracted question data is reasonable."""
        if not question_data:
            return False
            
        question = question_data.get('question', '')
        options = question_data.get('options', [])
        
        # Basic validation rules - less strict
        if len(question.strip()) < 5:  # Question too short (reduced from 10)
            self.logger.debug(f"Question too short: '{question}'")
            return False
            
        if len(question.strip()) > 1000:  # Question too long (increased from 500)
            self.logger.debug(f"Question too long: '{question[:50]}...'")
            return False
            
        if len(options) < 2:  # Need at least 2 options
            self.logger.debug(f"Not enough options: {len(options)}")
            return False
            
        # Check for obviously invalid patterns (less strict)
        question_lower = question.lower()
        critical_invalid_patterns = [
            'javascript:', 'onclick=', '<script', 'document.', 'window.',
            'function(', 'var ', 'alert(', 'console.log'
        ]
        
        for pattern in critical_invalid_patterns:
            if pattern in question_lower:
                self.logger.debug(f"Question contains invalid pattern '{pattern}': '{question}'")
                return False
        
        # Check if options look reasonable (less strict)
        valid_options = 0
        for option in options:
            option_clean = option.strip()
            if len(option_clean) >= 1 and len(option_clean) <= 500:  # Increased max length
                valid_options += 1
        
        if valid_options < 2:
            self.logger.debug(f"Not enough valid options: {valid_options}/{len(options)}")
            return False
        
        # Additional check: question should have some alphabetic content
        if not re.search(r'[a-zA-Z]{3,}', question):
            self.logger.debug(f"Question lacks alphabetic content: '{question}'")
            return False
        
        return True

    async def _extract_question_from_radio_group_improved(self, page: Page, name: str, radios: List, question_num: int) -> Optional[Dict[str, Any]]:
        """Improved extraction from radio input group with better question text detection."""
        try:
            # Try to find question text by traversing DOM structure
            first_radio = radios[0]
            
            # Strategy 1: Look for question text in form structure
            question_text = await first_radio.evaluate('''
                (el) => {
                    // Look for question text in various parent structures
                    let current = el;
                    
                    // Try to find a parent container that contains the question
                    for (let i = 0; i < 5; i++) {
                        if (current.parentElement) {
                            current = current.parentElement;
                            
                            // Look for text content that looks like a question
                            const textContent = current.textContent || '';
                            const lines = textContent.split('\\n').map(line => line.trim()).filter(line => line);
                            
                            for (const line of lines) {
                                // Skip if it's just radio button text or short fragments
                                if (line.length < 10 || line.length > 300) continue;
                                
                                // Look for question patterns
                                if ((line.includes('?') || line.match(/^\\d+\\./)) && 
                                    !line.toLowerCase().includes('click') &&
                                    !line.toLowerCase().includes('drag') &&
                                    !line.toLowerCase().includes('score')) {
                                    return line;
                                }
                            }
                        }
                    }
                    
                    // Fallback: look for any substantial text before the radio buttons
                    let walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    
                    let found = false;
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.parentElement && node.parentElement.contains(el)) {
                            found = true;
                        } else if (found && node.textContent.trim().length > 10) {
                            const text = node.textContent.trim();
                            if (text.includes('?') && text.length < 300) {
                                return text;
                            }
                        }
                    }
                    
                    return null;
                }
            ''')
            
            if question_text:
                question_text = re.sub(r'^\d+\.\s*', '', question_text.strip())
                
                # Extract options from radio buttons
                options = []
                for radio in radios:
                    # Get option text from value or associated label
                    option_text = await radio.evaluate('''
                        (el) => {
                            // Try to get text from label
                            const labels = document.querySelectorAll('label');
                            for (const label of labels) {
                                if (label.contains(el) || label.getAttribute('for') === el.id) {
                                    let text = label.textContent.replace(el.value, '').trim();
                                    // Remove radio button markers
                                    text = text.replace(/^[a-d]\\)\\s*/i, '').trim();
                                    if (text.length > 0) return text;
                                }
                            }
                            
                            // Fallback to value
                            return el.value || el.nextSibling?.textContent?.trim() || '';
                        }
                    ''')
                    
                    if option_text and option_text.strip():
                        options.append(option_text.strip())
                
                if len(options) >= 2:
                    return {
                        'question': question_text,
                        'options': options,
                        'questionNumber': str(question_num)
                    }
            
        except Exception as e:
            self.logger.debug(f"Error in improved radio group extraction: {e}")
        return None

    async def _extract_question_from_numbered_element_improved(self, page: Page, qel, question_num: int) -> Optional[Dict[str, Any]]:
        """Improved extraction from numbered elements with better validation."""
        try:
            question_text = await qel.inner_text()
            
            # Clean up question text
            question_text = re.sub(r'^\d+\.\s*', '', question_text.strip())
            
            # Validate this looks like a real question
            if len(question_text) < 10 or not re.search(r'[a-zA-Z]', question_text):
                return None
            
            # Find radio inputs for this question
            # Try multiple naming patterns and nearby elements
            radio_inputs = []
            
            # Pattern 1: Standard question naming
            for pattern in [f'q{question_num}', f'question{question_num}', f'q{question_num}_answer']:
                radios = await page.query_selector_all(f'input[name="{pattern}"]')
                if radios:
                    radio_inputs = radios
                    break
            
            # Pattern 2: Look for radio inputs near this element
            if not radio_inputs:
                radio_inputs = await qel.evaluate('''
                    (el) => {
                        const radios = [];
                        let current = el;
                        
                        // Look in next siblings
                        while (current.nextElementSibling && radios.length < 10) {
                            current = current.nextElementSibling;
                            const foundRadios = current.querySelectorAll('input[type="radio"]');
                            foundRadios.forEach(radio => radios.push(radio));
                            
                            // Stop if we find a reasonable number of radios or hit another question
                            if (radios.length >= 2 && radios.length <= 8) break;
                            if (current.textContent.match(/^\\d+\\./)) break;
                        }
                        
                        return radios;
                    }
                ''')
            
            options = []
            for radio in radio_inputs:
                if hasattr(radio, 'get_attribute'):  # Playwright element
                    value = await radio.get_attribute('value')
                else:  # From evaluate
                    value = radio.get('value') if hasattr(radio, 'get') else str(radio)
                
                if value and value.strip():
                    options.append(value.strip())
            
            if len(options) >= 2:
                return {
                    'question': question_text,
                    'options': options,
                    'questionNumber': str(question_num)
                }
            
        except Exception as e:
            self.logger.debug(f"Error in improved numbered element extraction: {e}")
        return None

    async def _extract_question_from_block(self, block, question_num: int) -> Optional[Dict[str, Any]]:
        """Extract question from a .questionBlock element with validation."""
        try:
            # Question text
            qtext_el = await block.query_selector('.q, .question, b, strong')
            if not qtext_el:
                return None
            
            question_text = await qtext_el.inner_text()
            question_text = re.sub(r'^\d+\.\s*', '', question_text.strip())
            
            # Options from radio inputs
            options = []
            radio_inputs = await block.query_selector_all('input[type="radio"]')
            for radio in radio_inputs:
                # Try to get label text
                option_text = await radio.evaluate('''
                    (el) => {
                        // Look for associated label
                        const label = el.closest('label') || 
                                     document.querySelector(`label[for="${el.id}"]`) ||
                                     el.parentNode;
                        
                        if (label) {
                            let text = label.textContent.trim();
                            // Remove the radio value if it's duplicated
                            text = text.replace(el.value, '').trim();
                            // Remove radio button markers like a), b), etc.
                            text = text.replace(/^[a-d]\\)\\s*/i, '').trim();
                            return text || el.value;
                        }
                        return el.value;
                    }
                ''')
                
                if option_text and option_text.strip():
                    options.append(option_text.strip())
            
            if question_text and len(options) >= 2:
                return {
                    'question': question_text,
                    'options': options,
                    'questionNumber': str(question_num)
                }
        except Exception as e:
            self.logger.debug(f"Error extracting from question block: {e}")
        return None

    async def _submit_quiz_and_get_results(self, page: Page, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Submit quiz answers and extract correct answers and hints from results page."""
        try:
            # Auto-select answers for all questions
            selected_count = 0
            for i, question in enumerate(questions):
                question_num = question.get('questionNumber', str(i+1))
                # Try different naming patterns
                for name_pattern in [f'q{question_num}', f'question{question_num}', f'q{i+1}']:
                    radios = await page.query_selector_all(f'input[name="{name_pattern}"]')
                    if radios:
                        await radios[0].click()  # Select first option
                        selected_count += 1
                        self.logger.debug(f"Selected answer for question {question_num}")
                        break
            
            self.logger.info(f"Selected answers for {selected_count}/{len(questions)} questions")
            
            if selected_count == 0:
                self.logger.warning("No radio buttons found to select - cannot submit quiz")
                return questions
            
            # Submit the quiz with multiple strategies
            submit_selectors = [
                'input[type="submit"][value*="Score"]',
                'input[type="submit"][value*="Submit"]', 
                'input[type="submit"][value*="Finish"]',
                'button[type="submit"]',
                'input[value*="Finish"]',
                'button:has-text("Submit")',
                'button:has-text("Finish")',
                '.submit-button'
            ]
            
            submit_btn = None
            for selector in submit_selectors:
                try:
                    submit_btn = await page.query_selector(selector)
                    if submit_btn:
                        # Check if button is visible and enabled
                        is_visible = await submit_btn.is_visible()
                        is_enabled = await submit_btn.is_enabled()
                        if is_visible and is_enabled:
                            self.logger.debug(f"Found submit button with selector: {selector}")
                            break
                        else:
                            submit_btn = None
                except Exception:
                    continue
            
            if submit_btn:
                try:
                    await submit_btn.click()
                    self.logger.info("Submitted quiz answers")
                    
                    # Wait for results page with longer timeout and multiple strategies
                    try:
                        # Strategy 1: Wait for network idle
                        await page.wait_for_load_state('networkidle', timeout=60000)
                    except Exception:
                        try:
                            # Strategy 2: Wait for specific result elements
                            await page.wait_for_selector('.results, .quiz-results, .score, .explanation', timeout=45000)
                        except Exception:
                            # Strategy 3: Just wait a bit and proceed
                            await asyncio.sleep(3)
                            self.logger.warning("Results page load timeout - proceeding with available content")
                    
                    # Extract results with correct answers and hints
                    return await self._parse_results_page(page, questions)
                    
                except Exception as e:
                    self.logger.warning(f"Error during quiz submission: {e}")
                    return questions
            else:
                self.logger.warning("No submit button found")
                return questions
                
        except Exception as e:
            self.logger.warning(f"Error submitting quiz: {e}")
            return questions

    async def _parse_results_page(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Parse the results page to extract correct answers and hints."""
        try:
            # Look for result blocks or question reviews
            result_selectors = ['.questionReview', '.questionTable', '.result-item', '.question-result']
            result_blocks = []
            
            for selector in result_selectors:
                result_blocks = await page.query_selector_all(selector)
                if result_blocks:
                    break
            
            if not result_blocks:
                self.logger.warning("No result blocks found, trying alternative parsing")
                return await self._parse_results_alternative(page, original_questions)
            
            self.logger.debug(f"Found {len(result_blocks)} result blocks")
            
            enhanced_questions = []
            for i, (question, result_block) in enumerate(zip(original_questions, result_blocks)):
                try:
                    # Extract correct answer
                    correct_answer = await self._extract_correct_answer(result_block)
                    
                    # Extract hint/explanation
                    hint = await self._extract_hint(result_block)
                    
                    # Create enhanced question
                    enhanced_question = question.copy()
                    enhanced_question['correct_answer'] = correct_answer or question['options'][0]
                    enhanced_question['hint'] = hint or ''
                    
                    enhanced_questions.append(enhanced_question)
                    
                except Exception as e:
                    self.logger.debug(f"Error processing result block {i}: {e}")
                    enhanced_questions.append(question)
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.warning(f"Error parsing results page: {e}")
            return original_questions

    async def _extract_correct_answer(self, result_block) -> Optional[str]:
        """Extract correct answer from a result block."""
        try:
            # Try multiple patterns for correct answer
            text = await result_block.inner_text()
            patterns = [
                r'Correct Answer:\s*(.+?)(?:\n|$)',
                r'Answer:\s*(.+?)(?:\n|$)',
                r'Correct:\s*(.+?)(?:\n|$)',
                r'Right Answer:\s*(.+?)(?:\n|$)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
            
            # Look for highlighted or bold correct answers
            correct_el = await result_block.query_selector('.correct, .right-answer, b:has-text("Correct")')
            if correct_el:
                return (await correct_el.inner_text()).strip()
                
        except Exception as e:
            self.logger.debug(f"Error extracting correct answer: {e}")
        return None

    async def _extract_hint(self, result_block) -> Optional[str]:
        """Extract hint/explanation from a result block."""
        try:
            # Look for explanation elements
            hint_selectors = ['.explanation', '.hint', '.trivia-fact', '.additional-info']
            for selector in hint_selectors:
                hint_el = await result_block.query_selector(selector)
                if hint_el:
                    return (await hint_el.inner_text()).strip()
            
            # Look for explanation patterns in text
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

    async def _parse_results_alternative(self, page: Page, original_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Alternative results parsing when standard selectors don't work."""
        try:
            # Get all page text and try to parse it
            page_text = await page.evaluate('document.body.innerText')
            
            # Split into lines and look for answer patterns
            lines = page_text.split('\n')
            enhanced_questions = []
            
            for i, question in enumerate(original_questions):
                enhanced_question = question.copy()
                
                # Look for correct answer in page text
                for line in lines:
                    if f"Question {i+1}" in line or f"{i+1}." in line:
                        # Look for answer patterns in nearby lines
                        for j in range(max(0, lines.index(line)), min(len(lines), lines.index(line) + 5)):
                            if "Correct" in lines[j] and "Answer" in lines[j]:
                                answer_match = re.search(r'Answer:\s*(.+)', lines[j])
                                if answer_match:
                                    enhanced_question['correct_answer'] = answer_match.group(1).strip()
                                    break
                
                if 'correct_answer' not in enhanced_question:
                    enhanced_question['correct_answer'] = question['options'][0]
                enhanced_question['hint'] = ''
                
                enhanced_questions.append(enhanced_question)
            
            return enhanced_questions
            
        except Exception as e:
            self.logger.warning(f"Alternative results parsing failed: {e}")
            return original_questions

    async def _extract_quiz_metadata(self, page: Page) -> Dict[str, str]:
        """Extract metadata about the quiz."""
        return {
            'difficulty': await self._get_quiz_difficulty(page),
            'domain': await self._get_quiz_domain(page),
            'topic': await self._get_quiz_topic(page)
        }

    async def _extract_questions_from_page(self, page: Page) -> List[Dict[str, Any]]:
        """Extract questions using primary and fallback methods."""
        # Try primary extraction method
        questions = await self._extract_all_questions_from_page(page)
        
        if not questions:
            self.logger.warning("No questions found using primary extraction method")
            # Try alternative extraction method
            questions = await self._extract_questions_alternative(page)
        
        return questions

    async def _process_extracted_questions(self, questions: List[Dict[str, Any]], descriptions: Dict[str, str], metadata: Dict[str, str]) -> List[Dict[str, Any]]:
        """Process and enhance extracted questions with metadata and descriptions."""
        processed_questions = []
        
        for i, question_data in enumerate(questions):
            if not question_data:
                continue
            
            # Classify question type using the dedicated classifier
            question_text = question_data['question']
            options = question_data['options']
            question_type = self.question_classifier.classify(question_text, options)
            question_data['type'] = question_type
            
            # Generate unique question ID
            question_id = self.indexer.get_next_id(question_type)
            
            # Add description if available
            question_number = question_data.get('questionNumber', str(i+1))
            description = descriptions.get(question_number, '')
            
            # Clean and process text fields
            cleaned_question = self.text_processor.clean_question_text(question_text)
            cleaned_description = self.text_processor.clean_description_text(description)
            
            # Handle image path for photo quiz questions
            image_path = ''
            if question_data.get('isPhotoQuiz') and question_data.get('imageUrl'):
                # Download image with proper question ID
                try:
                    image_path = await self.download_media(
                        question_data['imageUrl'], 
                        'image', 
                        question_id
                    )
                    if image_path:
                        self.logger.info(f"Downloaded image for question {question_id}: {image_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to download image for {question_id}: {e}")
                    image_path = question_data.get('image_path', '')
            
            # Update question data with all metadata
            question_data.update({
                "id": question_id,
                "question": cleaned_question,
                "difficulty": self.map_difficulty(metadata['difficulty']),
                "domain": self.map_domain(metadata['domain']),
                "topic": self.map_topic(metadata['topic']),
                "correct_answer": question_data.get('correct_answer', options[0] if options else ''),
                "hint": question_data.get('hint', ''),
                "description": cleaned_description,
                "media_path": image_path if image_path else question_data.get('media_path', '')
            })
            
            processed_questions.append(question_data)
            self.logger.debug(f"Processed question {i+1}: {cleaned_question[:50]}...")
        
        return processed_questions

    async def _get_quiz_difficulty(self, page: Page) -> str:
        """Get the quiz difficulty level - Updated selectors."""
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
            return difficulty
        except Exception as e:
            self.logger.debug(f"Error getting difficulty: {e}")
            return "Normal"

    async def _get_quiz_domain(self, page: Page) -> str:
        """Get the quiz domain/category from FunTrivia's main category (first level)."""
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
            return domain
        except Exception as e:
            self.logger.debug(f"Error getting domain: {e}")
            return "Culture"

    async def _get_quiz_topic(self, page: Page) -> str:
        """Get the quiz topic from FunTrivia's subcategory (second level)."""
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
                        const topicMatch = text.match(/(?:category|topic):\s*([^\\n\\r]{3,40})/i);
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
            return topic
        except Exception as e:
            self.logger.debug(f"Error getting topic: {e}")
            return "General"

    async def download_media(self, url: str, media_type: str, question_id: str) -> Optional[str]:
        """Download media file and return the local path."""
        import aiohttp # type: ignore
        import os
        from urllib.parse import urlparse
        
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10)
        )
        async def download_with_retry():
            # Parse URL to get file extension
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.split('.')
            ext = path_parts[-1].lower() if len(path_parts) > 1 else 'jpg'
            
            # Ensure valid extension
            if media_type == "image" and ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'
            elif media_type == "audio" and ext not in ['mp3', 'wav', 'ogg', 'm4a']:
                ext = 'mp3'
            
            # Determine directory and filename
            if media_type == "image":
                directory = self.config['storage']['images_dir']
                filename = f"{question_id}.{ext}"
            else:  # audio
                directory = self.config['storage']['audio_dir']
                filename = f"{question_id}.{ext}"
            
            filepath = os.path.join(directory, filename)
            
            # Download the file
            headers = {'User-Agent': self._get_random_user_agent()}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        os.makedirs(directory, exist_ok=True)
                        with open(filepath, 'wb') as f:
                            f.write(await response.read())
                        self.logger.info(f"Successfully downloaded {media_type} for {question_id}")
                        return f"assets/{media_type}s/{filename}"  # Return relative path for CSV
                    else:
                        raise Exception(f"Failed to download {media_type}: HTTP {response.status}")
        
        try:
            return await download_with_retry()
        except Exception as e:
            self.logger.error(f"Failed to download {media_type} for {question_id}: {e}")
            return None

    def map_difficulty(self, raw_difficulty: str) -> str:
        """Map FunTrivia difficulty to standardized value."""
        for std_difficulty, raw_values in self.mappings['difficulty_mapping'].items():
            if raw_difficulty.lower() in [v.lower() for v in raw_values]:
                return std_difficulty
        
        if self.strict_mapping:
            raise ValueError(f"Unknown difficulty level encountered: '{raw_difficulty}'. "
                           f"Please add this to the difficulty_mapping in config/mappings.json "
                           f"or run with --dump-categories-only to collect all categories first.")
        
        self.logger.warning(f"Unknown difficulty level: {raw_difficulty}, defaulting to Normal")
        return "Normal"

    def map_domain(self, raw_domain: str) -> str:
        """Map FunTrivia domain to standardized value."""
        for std_domain, raw_values in self.mappings['domain_mapping'].items():
            if raw_domain.lower() in [v.lower() for v in raw_values]:
                return std_domain
        
        if self.strict_mapping:
            raise ValueError(f"Unknown domain encountered: '{raw_domain}'. "
                           f"Please add this to the domain_mapping in config/mappings.json "
                           f"or run with --dump-categories-only to collect all categories first.")
        
        self.logger.warning(f"Unknown domain: {raw_domain}, defaulting to Culture")
        return "Culture"

    def map_topic(self, raw_topic: str) -> str:
        """Map FunTrivia topic to standardized value."""
        for std_topic, raw_values in self.mappings['topic_mapping'].items():
            if raw_topic.lower() in [v.lower() for v in raw_values]:
                return std_topic
        
        if self.strict_mapping:
            raise ValueError(f"Unknown topic encountered: '{raw_topic}'. "
                           f"Please add this to the topic_mapping in config/mappings.json "
                           f"or run with --dump-categories-only to collect all categories first.")
        
        self.logger.warning(f"Unknown topic: {raw_topic}, defaulting to General")
        return "General"

    async def _random_delay(self) -> None:
        """Add a random delay between requests to appear more human-like."""
        delay = random.uniform(RATE_LIMITS['random_delay_min'], RATE_LIMITS['random_delay_max'])
        await asyncio.sleep(delay)

    def _get_random_user_agent(self) -> str:
        """Get a random user agent string."""
        return random.choice(USER_AGENTS)

    async def _extract_descriptions_from_results(self, page: Page, questions: List[Dict[str, Any]]) -> Dict[str, str]:
        """Submit the quiz and extract descriptions/explanations from the results page."""
        try:
            # First, check if there's a submit button or if answers need to be selected
            submit_button = await page.query_selector('input[type="submit"], button[type="submit"], button:has-text("Submit"), input[value*="Submit"]')
            
            if not submit_button:
                self.logger.warning("No submit button found, trying to find other submission methods")
                # Try to find any button that might submit the quiz
                submit_button = await page.query_selector('button, input[type="button"]')
            
            if submit_button:
                # Select random answers for all questions to submit the quiz
                await self._select_quiz_answers(page, questions)
                
                # Submit the quiz
                self.logger.debug("Submitting quiz to get results page")
                await submit_button.click()
                
                # Wait for results page to load
                await page.wait_for_load_state('networkidle', timeout=30000)
                
                # Extract descriptions from results page
                descriptions = await self._extract_descriptions_from_page(page, questions)
                
                self.logger.info(f"Extracted {len(descriptions)} question descriptions from results page")
                return descriptions
            else:
                self.logger.warning("Could not find submit button, skipping description extraction")
                return {}
                
        except Exception as e:
            self.logger.warning(f"Error extracting descriptions from results: {e}")
            return {}

    async def _select_quiz_answers(self, page: Page, questions: List[Dict[str, Any]]) -> None:
        """Select random answers for all questions to enable quiz submission."""
        try:
            for question in questions:
                question_number = question.get('questionNumber')
                if question_number:
                    # Find radio buttons for this question
                    radio_buttons = await page.query_selector_all(f'input[name="q{question_number}"]')
                    if radio_buttons:
                        # Select the first option (we don't care about correctness, just need to submit)
                        await radio_buttons[0].click()
                        self.logger.debug(f"Selected answer for question {question_number}")
                        
        except Exception as e:
            self.logger.warning(f"Error selecting quiz answers: {e}")

    async def _extract_descriptions_from_page(self, page: Page, questions: List[Dict[str, Any]]) -> Dict[str, str]:
        """Extract descriptions/explanations from the current results page."""
        try:
            descriptions = await page.evaluate("""
                (questions) => {
                    const descriptions = {};
                    
                    // Strategy 1: Look for question-specific explanation sections
                    const explanationSelectors = [
                        '.question-explanation',
                        '.question-summary', 
                        '.explanation',
                        '.answer-explanation',
                        '.question-info',
                        '.trivia-fact',
                        '.additional-info'
                    ];
                    
                    // Try each selector
                    for (const selector of explanationSelectors) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            elements.forEach((el, index) => {
                                const text = el.textContent.trim();
                                if (text.length > 10) {
                                    descriptions[String(index + 1)] = text;
                                }
                            });
                            if (Object.keys(descriptions).length > 0) {
                                return descriptions;
                            }
                        }
                    }
                    
                    // Strategy 2: Look for numbered explanations that match question numbers
                    questions.forEach(question => {
                        const qNum = question.questionNumber;
                        
                        // Look for explanations that start with question number
                        const textNodes = document.evaluate(
                            `//text()[contains(., "${qNum}.") or contains(., "Question ${qNum}")]`,
                            document,
                            null,
                            XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE,
                            null
                        );
                        
                        for (let i = 0; i < textNodes.snapshotLength; i++) {
                            const node = textNodes.snapshotItem(i);
                            const parent = node.parentElement;
                            if (parent) {
                                const text = parent.textContent.trim();
                                // Look for explanation patterns
                                const explanationMatch = text.match(new RegExp(`${qNum}[.:]?\\s*(.{20,})`, 'i'));
                                if (explanationMatch && explanationMatch[1]) {
                                    descriptions[qNum] = explanationMatch[1].trim();
                                }
                            }
                        }
                    });
                    
                    // Strategy 3: Look for any informational text blocks
                    if (Object.keys(descriptions).length === 0) {
                        const infoElements = document.querySelectorAll('p, div, span');
                        let explanationTexts = [];
                        
                        infoElements.forEach(el => {
                            const text = el.textContent.trim();
                            // Filter out short texts and common UI elements
                            if (text.length > 30 && 
                                !text.toLowerCase().includes('score') &&
                                !text.toLowerCase().includes('back to') &&
                                !text.toLowerCase().includes('next quiz') &&
                                !text.toLowerCase().includes('copyright') &&
                                el.children.length === 0) { // Text-only elements
                                explanationTexts.push(text);
                            }
                        });
                        
                        // Assign explanations to questions based on order
                        explanationTexts.slice(0, questions.length).forEach((text, index) => {
                            descriptions[String(index + 1)] = text;
                        });
                    }
                    
                    return descriptions;
                }
            """, questions)
            
            return descriptions
            
        except Exception as e:
            self.logger.error(f"Error extracting descriptions from page: {e}")
            return {}

    async def _extract_all_questions_from_page(self, page: Page) -> List[Dict[str, Any]]:
        """Extract all questions from a single page (FunTrivia's format)."""
        try:
            # Extract all questions and their options using the actual FunTrivia structure
            questions_data = await page.evaluate("""
                () => {
                    const questions = [];
                    
                    // Find all question elements (numbered questions in bold)
                    const questionElements = Array.from(document.querySelectorAll('b')).filter(b => {
                        const text = b.textContent.trim();
                        return /^\d+\.\s/.test(text); // Starts with number and dot
                    });
                    
                    questionElements.forEach((questionEl, index) => {
                        const questionText = questionEl.textContent.trim();
                        const questionNumber = questionText.match(/^(\d+)\./)?.[1];
                        
                        if (!questionNumber) return;
                        
                        // Find radio buttons for this question
                        const radioButtons = Array.from(document.querySelectorAll(`input[name="q${questionNumber}"]`));
                        const options = radioButtons.map(radio => radio.value).filter(value => value && value.trim());
                        
                        if (questionText && options.length >= 2) {
                            // Clean up question text (remove number prefix)
                            const cleanQuestion = questionText.replace(/^\d+\.\s*/, '').trim();
                            
                            questions.push({
                                question: cleanQuestion,
                                options: options,
                                questionNumber: questionNumber
                            });
                        }
                    });
                    
                    return questions;
                }
            """)
            
            self.logger.info(f"Extracted {len(questions_data)} questions from page")
            return questions_data
            
        except Exception as e:
            self.logger.error(f"Error extracting questions from page: {e}")
            return []

    async def _extract_questions_alternative(self, page: Page) -> List[Dict[str, Any]]:
        """Alternative question extraction method for pages that don't match the standard format."""
        try:
            questions_data = await page.evaluate("""
                () => {
                    const questions = [];
                    
                    // Alternative strategy 1: Look for any numbered text that might be questions
                    const allText = document.body.innerText;
                    const lines = allText.split('\\n').map(line => line.trim()).filter(line => line);
                    
                    let currentQuestion = null;
                    let options = [];
                    
                    for (let i = 0; i < lines.length; i++) {
                        const line = lines[i];
                        
                        // Check if this line looks like a question (starts with number)
                        const questionMatch = line.match(/^(\\d+)\\.?\\s*(.+)/);
                        if (questionMatch && questionMatch[2].length > 10) {
                            // Save previous question if we have one
                            if (currentQuestion && options.length >= 2) {
                                questions.push({
                                    question: currentQuestion,
                                    options: options,
                                    questionNumber: questions.length + 1
                                });
                            }
                            
                            currentQuestion = questionMatch[2].trim();
                            options = [];
                        }
                        // Check if this line looks like an option (a), b), etc.)
                        else if (line.match(/^[a-d]\\)?\\s*.+/i) && currentQuestion) {
                            const optionText = line.replace(/^[a-d]\\)?\\s*/i, '').trim();
                            if (optionText.length > 0) {
                                options.push(optionText);
                            }
                        }
                    }
                    
                    // Don't forget the last question
                    if (currentQuestion && options.length >= 2) {
                        questions.push({
                            question: currentQuestion,
                            options: options,
                            questionNumber: questions.length + 1
                        });
                    }
                    
                    return questions;
                }
            """)
            
            self.logger.info(f"Alternative extraction found {len(questions_data)} questions")
            return questions_data
            
        except Exception as e:
            self.logger.error(f"Error in alternative question extraction: {e}")
            return [] 