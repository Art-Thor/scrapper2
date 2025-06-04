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
                processed_questions = self._process_extracted_questions(
                    results_with_answers, {}, quiz_metadata  # Empty descriptions dict for now
                )
                
                self.logger.info(f"Successfully processed {len(processed_questions)} questions from {quiz_url}")
                return processed_questions
                
        except Exception as e:
            self.logger.error(f"Error scraping quiz {quiz_url}: {e}")
            return []
        finally:
            await context.close()

    async def _extract_questions_robust(self, page: Page) -> List[Dict[str, Any]]:
        """Extract questions using multiple robust strategies."""
        questions = []
        
        # Strategy 1: Look for .questionBlock (newer FunTrivia format)
        try:
            question_blocks = await page.query_selector_all('.questionBlock')
            if question_blocks:
                self.logger.debug(f"Found {len(question_blocks)} .questionBlock elements")
                for i, block in enumerate(question_blocks):
                    question_data = await self._extract_question_from_block(block, i+1)
                    if question_data:
                        questions.append(question_data)
                if questions:
                    return questions
        except Exception as e:
            self.logger.debug(f"Strategy 1 (.questionBlock) failed: {e}")

        # Strategy 2: Look for numbered questions in bold tags
        try:
            bold_elements = await page.query_selector_all('b')
            question_elements = []
            for b in bold_elements:
                text = await b.inner_text()
                if re.match(r'^\d+\.\s', text.strip()):
                    question_elements.append(b)
            
            if question_elements:
                self.logger.debug(f"Found {len(question_elements)} numbered question elements")
                for i, qel in enumerate(question_elements):
                    question_data = await self._extract_question_from_numbered_element(page, qel, i+1)
                    if question_data:
                        questions.append(question_data)
                if questions:
                    return questions
        except Exception as e:
            self.logger.debug(f"Strategy 2 (numbered bold) failed: {e}")

        # Strategy 3: Look for radio input groups
        try:
            # Find all radio inputs and group by name attribute
            radio_inputs = await page.query_selector_all('input[type="radio"]')
            if radio_inputs:
                question_groups = {}
                for radio in radio_inputs:
                    name = await radio.get_attribute('name')
                    if name and name.startswith('q'):
                        if name not in question_groups:
                            question_groups[name] = []
                        question_groups[name].append(radio)
                
                self.logger.debug(f"Found {len(question_groups)} radio input groups")
                for i, (name, radios) in enumerate(question_groups.items(), 1):
                    question_data = await self._extract_question_from_radio_group(page, name, radios, i)
                    if question_data:
                        questions.append(question_data)
                if questions:
                    return questions
        except Exception as e:
            self.logger.debug(f"Strategy 3 (radio groups) failed: {e}")

        self.logger.warning("All question extraction strategies failed")
        return questions

    async def _extract_question_from_block(self, block, question_num: int) -> Optional[Dict[str, Any]]:
        """Extract question from a .questionBlock element."""
        try:
            # Question text
            qtext_el = await block.query_selector('.q, .question, b')
            if not qtext_el:
                return None
            
            question_text = await qtext_el.inner_text()
            question_text = re.sub(r'^\d+\.\s*', '', question_text.strip())
            
            # Options from radio inputs
            options = []
            radio_inputs = await block.query_selector_all('input[type="radio"]')
            for radio in radio_inputs:
                # Try to get label text
                label_text = await radio.evaluate('''
                    (el) => {
                        const label = el.closest('label') || el.parentNode;
                        return label ? label.innerText.trim() : el.value;
                    }
                ''')
                if label_text:
                    # Clean option text (remove radio button markers)
                    clean_option = re.sub(r'^[a-d]\)\s*', '', label_text.strip(), flags=re.IGNORECASE)
                    options.append(clean_option)
            
            if question_text and len(options) >= 2:
                return {
                    'question': question_text,
                    'options': options,
                    'questionNumber': str(question_num)
                }
        except Exception as e:
            self.logger.debug(f"Error extracting from question block: {e}")
        return None

    async def _extract_question_from_numbered_element(self, page: Page, qel, question_num: int) -> Optional[Dict[str, Any]]:
        """Extract question from a numbered bold element."""
        try:
            question_text = await qel.inner_text()
            question_text = re.sub(r'^\d+\.\s*', '', question_text.strip())
            
            # Find radio inputs for this question number
            radio_inputs = await page.query_selector_all(f'input[name="q{question_num}"], input[name="question{question_num}"]')
            
            options = []
            for radio in radio_inputs:
                value = await radio.get_attribute('value')
                if value:
                    options.append(value.strip())
            
            if question_text and len(options) >= 2:
                return {
                    'question': question_text,
                    'options': options,
                    'questionNumber': str(question_num)
                }
        except Exception as e:
            self.logger.debug(f"Error extracting numbered question: {e}")
        return None

    async def _extract_question_from_radio_group(self, page: Page, name: str, radios: List, question_num: int) -> Optional[Dict[str, Any]]:
        """Extract question from a radio input group."""
        try:
            # Try to find question text near the first radio
            first_radio = radios[0]
            
            # Look for question text in nearby elements
            question_text = await first_radio.evaluate('''
                (el) => {
                    // Look for question text in preceding elements
                    let current = el;
                    while (current && current.previousElementSibling) {
                        current = current.previousElementSibling;
                        const text = current.innerText || current.textContent;
                        if (text && text.trim().length > 10) {
                            return text.trim();
                        }
                    }
                    return null;
                }
            ''')
            
            if question_text:
                question_text = re.sub(r'^\d+\.\s*', '', question_text.strip())
            else:
                question_text = f"Question {question_num}"
            
            options = []
            for radio in radios:
                value = await radio.get_attribute('value')
                if value:
                    options.append(value.strip())
            
            if len(options) >= 2:
                return {
                    'question': question_text,
                    'options': options,
                    'questionNumber': str(question_num)
                }
        except Exception as e:
            self.logger.debug(f"Error extracting from radio group: {e}")
        return None

    async def _submit_quiz_and_get_results(self, page: Page, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Submit quiz answers and extract correct answers and hints from results page."""
        try:
            # Auto-select answers for all questions
            for i, question in enumerate(questions):
                question_num = question.get('questionNumber', str(i+1))
                # Try different naming patterns
                for name_pattern in [f'q{question_num}', f'question{question_num}', f'q{i+1}']:
                    radios = await page.query_selector_all(f'input[name="{name_pattern}"]')
                    if radios:
                        await radios[0].click()  # Select first option
                        break
            
            # Submit the quiz
            submit_selectors = [
                'input[type="submit"][value*="Score"]',
                'input[type="submit"][value*="Submit"]',
                'button[type="submit"]',
                'input[value*="Finish"]'
            ]
            
            submit_btn = None
            for selector in submit_selectors:
                submit_btn = await page.query_selector(selector)
                if submit_btn:
                    break
            
            if submit_btn:
                await submit_btn.click()
                self.logger.info("Submitted quiz answers")
                await page.wait_for_load_state('networkidle', timeout=TIMEOUTS['results_wait'])
                
                # Extract results with correct answers and hints
                return await self._parse_results_page(page, questions)
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

    def _process_extracted_questions(self, questions: List[Dict[str, Any]], descriptions: Dict[str, str], metadata: Dict[str, str]) -> List[Dict[str, Any]]:
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
            
            # Update question data with all metadata
            question_data.update({
                "id": question_id,
                "question": cleaned_question,
                "difficulty": self.map_difficulty(metadata['difficulty']),
                "domain": self.map_domain(metadata['domain']),
                "topic": self.map_topic(metadata['topic']),
                "correct_answer": question_data.get('correct_answer', options[0] if options else ''),
                "hint": question_data.get('hint', ''),
                "description": cleaned_description
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