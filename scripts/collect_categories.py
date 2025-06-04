#!/usr/bin/env python3
"""
Category Collection Script for FunTrivia Scraper

This script traverses the FunTrivia website and collects all unique categories,
domains, and topics encountered. The collected data is saved to JSON/CSV files
for manual review and mapping.

Usage:
    python collect_categories.py [--output-format json|csv|both] [--config config/settings.json]
"""

import asyncio
import argparse
import json
import csv
import logging
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict, Counter
import sys
import os

# Add src to path for imports
sys.path.append('src')

from scraper.funtrivia import FunTriviaScraper
from utils.rate_limiter import RateLimiter

class CategoryCollector:
    """Collects and analyzes categories from FunTrivia website."""
    
    def __init__(self, config_path: str = "config/settings.json"):
        self.config_path = config_path
        self.categories_data = {
            'raw_domains': Counter(),
            'raw_topics': Counter(), 
            'raw_difficulties': Counter(),
            'category_urls': set(),
            'quiz_urls_by_category': defaultdict(list),
            'domain_topic_combinations': defaultdict(set),
            'url_patterns': defaultdict(list)
        }
        # Initialize specific keys to avoid KeyError
        self.categories_data['url_patterns']['main_page'] = []
        self.categories_data['url_patterns']['categories'] = []
        self.setup_logging()
        
    def setup_logging(self):
        """Set up logging for the collector."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/category_collection.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def save_progress(self, filename: str = "category_collection_progress.json"):
        """Save current progress to allow resuming if interrupted."""
        try:
            # Convert sets to lists for JSON serialization
            progress_data = {}
            for key, value in self.categories_data.items():
                if key == 'category_urls':
                    progress_data[key] = list(value)
                elif key == 'raw_domains' or key == 'raw_topics' or key == 'raw_difficulties':
                    progress_data[key] = dict(value)
                elif key == 'domain_topic_combinations':
                    progress_data[key] = {k: list(v) for k, v in value.items()}
                else:
                    progress_data[key] = value
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"Progress saved to {filename}")
        except Exception as e:
            self.logger.warning(f"Failed to save progress: {e}")

    def load_progress(self, filename: str = "category_collection_progress.json") -> bool:
        """Load previous progress if available."""
        try:
            if not os.path.exists(filename):
                return False
            
            with open(filename, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
            
            # Convert lists back to appropriate types
            for key, value in progress_data.items():
                if key == 'category_urls':
                    self.categories_data[key] = set(value)
                elif key == 'raw_domains' or key == 'raw_topics' or key == 'raw_difficulties':
                    self.categories_data[key] = Counter(value)
                elif key == 'domain_topic_combinations':
                    self.categories_data[key] = defaultdict(set)
                    for k, v in value.items():
                        self.categories_data[key][k] = set(v)
                else:
                    self.categories_data[key] = value
            
            self.logger.info(f"Loaded previous progress from {filename}")
            return True
        except Exception as e:
            self.logger.warning(f"Failed to load progress: {e}")
            return False

    async def collect_all_categories(self) -> Dict[str, Any]:
        """
        Main method to collect all categories from the site.
        
        Returns:
            Dictionary containing all collected category data
        """
        self.logger.info("Starting comprehensive category collection")
        
        # Try to load previous progress
        progress_loaded = self.load_progress()
        if progress_loaded:
            self.logger.info("Resuming from previous progress")
        
        # Initialize scraper without mappings to get raw data
        scraper = FunTriviaScraper(self.config_path)
        
        try:
            await scraper.initialize()
            
            # Step 1: Get all category URLs from main page (skip if we have them)
            if not self.categories_data['category_urls']:
                self.logger.info("Collecting category URLs...")
                category_urls = await self._get_all_category_urls(scraper)
                self.categories_data['category_urls'] = category_urls
                self.save_progress()  # Save after getting URLs
            else:
                category_urls = list(self.categories_data['category_urls'])
                
            self.logger.info(f"Found {len(category_urls)} category URLs")
            
            if not category_urls:
                self.logger.error("No category URLs found - aborting")
                return self.categories_data
            
            # Step 2: For each category, collect quiz URLs and analyze structure
            self.logger.info("Analyzing category structure...")
            successful_analyses = 0
            failed_analyses = 0
            skipped_analyses = 0
            
            # Check which categories we've already analyzed
            analyzed_categories = set()
            for category_info in self.categories_data['url_patterns']['categories']:
                if isinstance(category_info, dict) and 'url' in category_info:
                    analyzed_categories.add(category_info['url'])
            
            for i, category_url in enumerate(category_urls, 1):
                try:
                    if category_url in analyzed_categories:
                        self.logger.info(f"Skipping already analyzed category {i}/{len(category_urls)}: {category_url}")
                        skipped_analyses += 1
                        continue
                    
                    self.logger.info(f"Processing category {i}/{len(category_urls)}: {category_url}")
                    await self._analyze_category(scraper, category_url)
                    successful_analyses += 1
                    
                    # Save progress every 5 successful analyses
                    if successful_analyses % 5 == 0:
                        self.save_progress()
                    
                    # Add delay between requests to be respectful
                    await asyncio.sleep(2)  # Increased delay
                    
                except Exception as e:
                    self.logger.warning(f"Failed to analyze category {category_url}: {e}")
                    failed_analyses += 1
                    # Continue with next category instead of stopping
                    continue
            
            self.logger.info(f"Category analysis complete: {successful_analyses} successful, {failed_analyses} failed, {skipped_analyses} skipped")
            
            # Save progress after category analysis
            self.save_progress()
            
            # Step 3: Sample quiz pages to extract domain/topic patterns
            if successful_analyses > 0 or skipped_analyses > 0:
                self.logger.info("Sampling quiz pages for metadata...")
                try:
                    await self._sample_quiz_metadata(scraper)
                    self.save_progress()  # Save after sampling
                except Exception as e:
                    self.logger.warning(f"Quiz metadata sampling failed: {e} - continuing anyway")
            
            # Step 4: Generate summary statistics
            summary = self._generate_summary()
            self.categories_data['summary'] = summary
            
            # Final save
            self.save_progress()
            
            self.logger.info("Category collection completed successfully")
            return self.categories_data
            
        except KeyboardInterrupt:
            self.logger.info("Collection interrupted by user - saving progress")
            self.save_progress()
            raise
        except Exception as e:
            self.logger.error(f"Critical error during category collection: {e}")
            self.save_progress()  # Save what we have so far
            raise
        finally:
            try:
                await scraper.close()
            except Exception as e:
                self.logger.debug(f"Error closing scraper: {e}")
    
    async def _get_all_category_urls(self, scraper: FunTriviaScraper) -> List[str]:
        """Extract all category URLs from the main quizzes page."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        context = None
        page = None
        
        try:
            context = await scraper.browser.new_context(
                user_agent=scraper._get_random_user_agent()
            )
            page = await context.new_page()
            
            # Load main quizzes page with increased timeout
            await page.goto(f"{scraper.config['scraper']['base_url']}/quizzes/", 
                          timeout=60000)  # Increased to 60 seconds
            await page.wait_for_load_state('networkidle', timeout=45000)  # Increased timeout
            
            # Extract all category links with more comprehensive selectors
            category_data = await page.evaluate("""
                () => {
                    const categories = new Set();
                    const patterns = [];
                    
                    // Strategy 1: Links in category navigation
                    document.querySelectorAll('a[href*="/quizzes/"]').forEach(link => {
                        const href = link.href;
                        const text = link.textContent.trim();
                        categories.add(href);
                        patterns.push({url: href, text: text, context: 'navigation'});
                    });
                    
                    // Strategy 2: Category listing pages
                    document.querySelectorAll('a[href*="/category/"], a[href*="/topic/"]').forEach(link => {
                        const href = link.href;
                        const text = link.textContent.trim();
                        categories.add(href);
                        patterns.push({url: href, text: text, context: 'category_list'});
                    });
                    
                    // Strategy 3: Browse by subject links
                    document.querySelectorAll('a').forEach(link => {
                        const href = link.href;
                        const text = link.textContent.trim().toLowerCase();
                        
                        if (href.includes('/quizzes/') && 
                            (text.includes('browse') || text.includes('category') || 
                             text.includes('subject') || text.includes('topic'))) {
                            categories.add(href);
                            patterns.push({url: href, text: text, context: 'browse'});
                        }
                    });
                    
                    return {
                        categories: Array.from(categories),
                        patterns: patterns
                    };
                }
            """)
            
            # Store URL patterns for analysis
            self.categories_data['url_patterns']['main_page'] = category_data['patterns']
            
            return category_data['categories']
            
        except PlaywrightTimeoutError:
            self.logger.error("Timeout while loading main categories page")
            return []
        except Exception as e:
            self.logger.error(f"Error getting category URLs: {e}")
            return []
        finally:
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
            except Exception as e:
                self.logger.debug(f"Error closing page/context in _get_all_category_urls: {e}")
    
    async def _analyze_category(self, scraper: FunTriviaScraper, category_url: str):
        """Analyze a single category page to extract structure and quiz links."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        context = None
        page = None
        
        try:
            context = await scraper.browser.new_context(
                user_agent=scraper._get_random_user_agent()
            )
            page = await context.new_page()
            
            # Increased timeouts and added retry logic
            await page.goto(category_url, timeout=60000)  # Increased to 60 seconds
            await page.wait_for_load_state('networkidle', timeout=45000)  # Increased timeout
            
            # Extract category metadata and quiz links
            category_info = await page.evaluate("""
                () => {
                    const info = {
                        url: window.location.href,
                        path_segments: window.location.pathname.split('/').filter(s => s),
                        title: document.title,
                        h1_text: '',
                        quiz_links: [],
                        subcategory_links: [],
                        breadcrumbs: []
                    };
                    
                    // Get main heading
                    const h1 = document.querySelector('h1');
                    if (h1) info.h1_text = h1.textContent.trim();
                    
                    // Get breadcrumbs if available
                    document.querySelectorAll('.breadcrumb a, .breadcrumbs a, nav a').forEach(link => {
                        info.breadcrumbs.push(link.textContent.trim());
                    });
                    
                    // Get quiz links
                    document.querySelectorAll('a[href*="/quiz/"]').forEach(link => {
                        info.quiz_links.push({
                            url: link.href,
                            text: link.textContent.trim()
                        });
                    });
                    
                    // Get subcategory links
                    document.querySelectorAll('a[href*="/quizzes/"]').forEach(link => {
                        if (link.href !== info.url) {
                            info.subcategory_links.push({
                                url: link.href,
                                text: link.textContent.trim()
                            });
                        }
                    });
                    
                    return info;
                }
            """)
            
            # Store the analysis
            self.categories_data['quiz_urls_by_category'][category_url] = category_info['quiz_links']
            self.categories_data['url_patterns']['categories'].append(category_info)
            
            # Extract domain/topic hints from URL structure
            self._analyze_url_structure(category_url, category_info)
            
        except PlaywrightTimeoutError:
            self.logger.warning(f"Timeout while analyzing category {category_url} - skipping")
        except Exception as e:
            self.logger.warning(f"Error analyzing category {category_url}: {e} - skipping")
        finally:
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
            except Exception as e:
                self.logger.debug(f"Error closing page/context in _analyze_category: {e}")
    
    def _analyze_url_structure(self, category_url: str, category_info: Dict[str, Any]):
        """Analyze URL structure to extract potential domains/topics."""
        from urllib.parse import urlparse
        
        parsed = urlparse(category_url)
        path_segments = [s for s in parsed.path.split('/') if s and s != 'quizzes']
        
        # Common domain indicators in URLs
        domain_indicators = {
            'animals': 'Nature',
            'science': 'Science', 
            'geography': 'Geography',
            'history': 'History',
            'sports': 'Sports',
            'entertainment': 'Culture',
            'music': 'Culture',
            'movies': 'Culture',
            'literature': 'Culture',
            'people': 'Culture'
        }
        
        for segment in path_segments:
            segment_lower = segment.lower()
            
            # Check if segment matches known domain
            if segment_lower in domain_indicators:
                self.categories_data['raw_domains'][domain_indicators[segment_lower]] += 1
            else:
                # Add as potential new domain
                self.categories_data['raw_domains'][segment.title()] += 1
            
            # Add as potential topic
            topic_name = segment.replace('_', ' ').replace('-', ' ').title()
            self.categories_data['raw_topics'][topic_name] += 1
        
        # Analyze page title for additional hints
        if category_info.get('title'):
            title_words = category_info['title'].lower().split()
            for word in title_words:
                if word in domain_indicators:
                    self.categories_data['raw_domains'][domain_indicators[word]] += 1
        
        # Analyze h1 text
        if category_info.get('h1_text'):
            h1_clean = category_info['h1_text'].replace(' Trivia', '').replace(' Quiz', '').strip()
            if h1_clean:
                self.categories_data['raw_topics'][h1_clean] += 1
    
    async def _sample_quiz_metadata(self, scraper: FunTriviaScraper, max_samples: int = 25):
        """Sample quiz pages to extract actual domain/topic metadata."""
        all_quiz_urls = []
        
        # Collect quiz URLs from all categories
        for quiz_list in self.categories_data['quiz_urls_by_category'].values():
            all_quiz_urls.extend([quiz['url'] for quiz in quiz_list])
        
        if not all_quiz_urls:
            self.logger.warning("No quiz URLs found for sampling")
            return
        
        # Sample a smaller subset for analysis to avoid timeouts
        import random
        sample_size = min(max_samples, len(all_quiz_urls))
        sample_urls = random.sample(all_quiz_urls, sample_size)
        
        self.logger.info(f"Sampling {len(sample_urls)} quiz pages for metadata...")
        
        successful_samples = 0
        failed_samples = 0
        
        for i, quiz_url in enumerate(sample_urls, 1):
            try:
                self.logger.info(f"Sampling quiz {i}/{len(sample_urls)}: {quiz_url[:50]}...")
                metadata = await self._extract_quiz_metadata(scraper, quiz_url)
                
                if metadata:
                    self.categories_data['raw_domains'][metadata['domain']] += 1
                    self.categories_data['raw_topics'][metadata['topic']] += 1
                    self.categories_data['raw_difficulties'][metadata['difficulty']] += 1
                    
                    # Track domain-topic combinations
                    self.categories_data['domain_topic_combinations'][metadata['domain']].add(metadata['topic'])
                    successful_samples += 1
                else:
                    failed_samples += 1
                
                # Increase delay between requests to be more respectful
                await asyncio.sleep(1.5)
                
            except Exception as e:
                self.logger.warning(f"Error sampling quiz {quiz_url}: {e}")
                failed_samples += 1
                # Continue with next quiz instead of stopping
                continue
        
        self.logger.info(f"Quiz sampling complete: {successful_samples} successful, {failed_samples} failed")
    
    async def _extract_quiz_metadata(self, scraper: FunTriviaScraper, quiz_url: str) -> Dict[str, str]:
        """Extract metadata from a single quiz page."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        context = None
        page = None
        
        try:
            context = await scraper.browser.new_context(
                user_agent=scraper._get_random_user_agent()
            )
            page = await context.new_page()
            
            await page.goto(quiz_url, timeout=45000)  # Increased timeout
            await page.wait_for_load_state('networkidle', timeout=30000)
            
            # Use the same extraction methods as the main scraper
            difficulty = await scraper._get_quiz_difficulty(page)
            domain = await scraper._get_quiz_domain(page)
            topic = await scraper._get_quiz_topic(page)
            
            return {
                'difficulty': difficulty,
                'domain': domain,
                'topic': topic,
                'url': quiz_url
            }
            
        except PlaywrightTimeoutError:
            self.logger.debug(f"Timeout extracting metadata from {quiz_url}")
            return None
        except Exception as e:
            self.logger.debug(f"Error extracting metadata from {quiz_url}: {e}")
            return None
        finally:
            try:
                if page:
                    await page.close()
                if context:
                    await context.close()
            except Exception as e:
                self.logger.debug(f"Error closing page/context in _extract_quiz_metadata: {e}")
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics of collected data."""
        summary = {
            'total_category_urls': len(self.categories_data['category_urls']),
            'total_quiz_urls': sum(len(quizzes) for quizzes in self.categories_data['quiz_urls_by_category'].values()),
            'unique_domains': len(self.categories_data['raw_domains']),
            'unique_topics': len(self.categories_data['raw_topics']),
            'unique_difficulties': len(self.categories_data['raw_difficulties']),
            'top_domains': dict(self.categories_data['raw_domains'].most_common(10)),
            'top_topics': dict(self.categories_data['raw_topics'].most_common(20)),
            'domain_topic_mapping': {
                domain: list(topics) 
                for domain, topics in self.categories_data['domain_topic_combinations'].items()
            }
        }
        return summary
    
    def save_to_json(self, output_file: str = "all_categories.json"):
        """Save collected data to JSON file."""
        # Convert sets to lists for JSON serialization
        data_to_save = {}
        for key, value in self.categories_data.items():
            if key == 'category_urls':
                data_to_save[key] = list(value)
            elif key == 'raw_domains' or key == 'raw_topics' or key == 'raw_difficulties':
                data_to_save[key] = dict(value)
            elif key == 'domain_topic_combinations':
                data_to_save[key] = {k: list(v) for k, v in value.items()}
            else:
                data_to_save[key] = value
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Saved category data to {output_file}")
    
    def save_to_csv(self, output_dir: str = "output"):
        """Save collected data to multiple CSV files."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Save domains
        domains_file = output_path / "collected_domains.csv"
        with open(domains_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Domain', 'Count', 'Status'])
            for domain, count in self.categories_data['raw_domains'].most_common():
                writer.writerow([domain, count, 'needs_review'])
        
        # Save topics
        topics_file = output_path / "collected_topics.csv"
        with open(topics_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Topic', 'Count', 'Status', 'Suggested_Domain'])
            for topic, count in self.categories_data['raw_topics'].most_common():
                writer.writerow([topic, count, 'needs_review', ''])
        
        # Save domain-topic combinations
        combinations_file = output_path / "domain_topic_combinations.csv"
        with open(combinations_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Domain', 'Topics'])
            for domain, topics in self.categories_data['domain_topic_combinations'].items():
                writer.writerow([domain, '; '.join(topics)])
        
        # Save category URLs
        urls_file = output_path / "category_urls.csv"
        with open(urls_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Category_URL', 'Quiz_Count'])
            for cat_url, quizzes in self.categories_data['quiz_urls_by_category'].items():
                writer.writerow([cat_url, len(quizzes)])
        
        self.logger.info(f"Saved CSV files to {output_dir}/")
    
    def print_summary(self):
        """Print a summary of collected categories."""
        summary = self.categories_data['summary']
        
        print("\n" + "="*60)
        print("CATEGORY COLLECTION SUMMARY")
        print("="*60)
        print(f"Total category URLs found: {summary['total_category_urls']}")
        print(f"Total quiz URLs found: {summary['total_quiz_urls']}")
        print(f"Unique domains found: {summary['unique_domains']}")
        print(f"Unique topics found: {summary['unique_topics']}")
        
        print(f"\nTop 10 Domains:")
        for domain, count in summary['top_domains'].items():
            print(f"  {domain}: {count}")
        
        print(f"\nTop 20 Topics:")
        for topic, count in summary['top_topics'].items():
            print(f"  {topic}: {count}")
        
        print(f"\nDomain-Topic Combinations:")
        for domain, topics in summary['domain_topic_mapping'].items():
            print(f"  {domain}: {len(topics)} topics")
        
        print("="*60)


async def main():
    parser = argparse.ArgumentParser(description='Collect all categories from FunTrivia')
    parser.add_argument('--output-format', choices=['json', 'csv', 'both'], default='both',
                      help='Output format for collected data')
    parser.add_argument('--config', default='config/settings.json',
                      help='Path to configuration file')
    parser.add_argument('--output-dir', default='output',
                      help='Output directory for files')
    parser.add_argument('--fresh-start', action='store_true',
                      help='Start fresh, ignoring any previous progress')
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Handle fresh start option
    progress_file = "category_collection_progress.json"
    if args.fresh_start and os.path.exists(progress_file):
        os.remove(progress_file)
        print(f"🗑️  Removed previous progress file: {progress_file}")
    
    collector = CategoryCollector(args.config)
    
    try:
        print("🔍 Starting category collection...")
        print("This process may take 10-20 minutes depending on site responsiveness.")
        print("The script will save progress periodically and can resume if interrupted.")
        print("-" * 60)
        
        await collector.collect_all_categories()
        
        # Save data in requested format(s)
        if args.output_format in ['json', 'both']:
            json_file = Path(args.output_dir) / "all_categories.json"
            collector.save_to_json(str(json_file))
        
        if args.output_format in ['csv', 'both']:
            collector.save_to_csv(args.output_dir)
        
        # Print summary
        collector.print_summary()
        
        # Clean up progress file on successful completion
        if os.path.exists(progress_file):
            os.remove(progress_file)
            print(f"\n🧹 Cleaned up progress file: {progress_file}")
        
        print(f"\n✅ Category collection completed successfully!")
        print(f"📁 Files saved to: {args.output_dir}/")
        print(f"📝 Review the collected categories and update your mappings accordingly.")
        
    except KeyboardInterrupt:
        print(f"\n⏹️  Collection interrupted by user")
        print(f"📄 Progress saved. Run the script again to resume from where you left off.")
        print(f"💡 Use --fresh-start flag if you want to start over completely.")
    except Exception as e:
        print(f"\n❌ Error during collection: {e}")
        print(f"📄 Progress saved. You can resume by running the script again.")
        print(f"📝 Check logs/category_collection.log for detailed error information.")
        logging.getLogger(__name__).error(f"Collection failed: {e}", exc_info=True)


if __name__ == '__main__':
    asyncio.run(main()) 