import requests
import urllib.robotparser
from urllib.parse import urljoin, urlparse
import time
from typing import Dict, List, Optional, Tuple
import logging
import json
from datetime import datetime, timedelta

class RobotsChecker:
    """Checks and enforces robots.txt compliance."""
    
    def __init__(self, base_url: str):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url.rstrip('/')
        self.robots_url = urljoin(self.base_url, '/robots.txt')
        self.rp = urllib.robotparser.RobotFileParser()
        self.last_check = None
        self.check_interval = 3600  # Re-check robots.txt every hour
        self.user_agent = '*'
        
    def fetch_robots_txt(self) -> bool:
        """Fetch and parse robots.txt file."""
        try:
            self.logger.info(f"Fetching robots.txt from {self.robots_url}")
            
            # Set the URL and read the robots.txt
            self.rp.set_url(self.robots_url)
            self.rp.read()
            
            self.last_check = time.time()
            self.logger.info("Successfully parsed robots.txt")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to fetch robots.txt: {e}")
            # If we can't fetch robots.txt, assume we can crawl (common practice)
            return False
    
    def can_fetch(self, url: str, user_agent: str = None) -> bool:
        """Check if we can fetch the given URL according to robots.txt."""
        if user_agent is None:
            user_agent = self.user_agent
            
        # Re-fetch robots.txt if it's been too long
        if (self.last_check is None or 
            time.time() - self.last_check > self.check_interval):
            self.fetch_robots_txt()
        
        try:
            can_crawl = self.rp.can_fetch(user_agent, url)
            if not can_crawl:
                self.logger.warning(f"robots.txt disallows crawling: {url}")
            return can_crawl
        except:
            # If robots.txt parsing fails, assume we can crawl
            return True
    
    def get_crawl_delay(self, user_agent: str = None) -> Optional[float]:
        """Get the crawl delay specified in robots.txt."""
        if user_agent is None:
            user_agent = self.user_agent
            
        try:
            delay = self.rp.crawl_delay(user_agent)
            if delay:
                self.logger.info(f"robots.txt specifies crawl delay: {delay} seconds")
            return delay
        except:
            return None
    
    def get_robots_summary(self) -> Dict[str, any]:
        """Get a summary of robots.txt rules."""
        if self.last_check is None:
            self.fetch_robots_txt()
        
        try:
            # This is a simplified summary - urllib.robotparser doesn't expose all details
            summary = {
                'robots_url': self.robots_url,
                'last_checked': datetime.fromtimestamp(self.last_check).isoformat() if self.last_check else None,
                'can_fetch_base': self.can_fetch(self.base_url),
                'crawl_delay': self.get_crawl_delay(),
                'user_agent': self.user_agent
            }
            
            # Test common paths
            test_paths = ['/quizzes/', '/quiz/', '/categories/']
            for path in test_paths:
                test_url = urljoin(self.base_url, path)
                summary[f'can_fetch_{path.strip("/")}'] = self.can_fetch(test_url)
            
            return summary
        except Exception as e:
            self.logger.error(f"Error generating robots summary: {e}")
            return {'error': str(e)}

class EthicalScraper:
    """Implements ethical scraping practices and rate limiting."""
    
    def __init__(self, base_url: str, config: Dict[str, any]):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.config = config
        self.robots_checker = RobotsChecker(base_url)
        self.request_history = []
        self.session_start = time.time()
        
        # Ethical scraping parameters
        self.min_delay = config.get('ethical_scraping', {}).get('min_delay_seconds', 1.0)
        self.max_requests_per_minute = config.get('ethical_scraping', {}).get('max_requests_per_minute', 30)
        self.max_requests_per_hour = config.get('ethical_scraping', {}).get('max_requests_per_hour', 1000)
        self.respect_crawl_delay = config.get('ethical_scraping', {}).get('respect_crawl_delay', True)
        
    def check_compliance(self, url: str) -> Tuple[bool, str]:
        """Check if accessing a URL complies with ethical scraping rules."""
        # Check robots.txt
        if not self.robots_checker.can_fetch(url):
            return False, f"robots.txt disallows access to {url}"
        
        # Check rate limiting
        if not self._check_rate_limits():
            return False, "Rate limit exceeded - too many requests"
        
        # Check robots.txt crawl delay
        if self.respect_crawl_delay:
            crawl_delay = self.robots_checker.get_crawl_delay()
            if crawl_delay and self._get_time_since_last_request() < crawl_delay:
                return False, f"Must wait {crawl_delay} seconds between requests (robots.txt)"
        
        # Check minimum delay
        if self._get_time_since_last_request() < self.min_delay:
            return False, f"Must wait at least {self.min_delay} seconds between requests"
        
        return True, "OK"
    
    def _check_rate_limits(self) -> bool:
        """Check if we're within rate limits."""
        current_time = time.time()
        
        # Clean old requests from history
        self.request_history = [
            req_time for req_time in self.request_history
            if current_time - req_time < 3600  # Keep last hour
        ]
        
        # Check requests per minute
        recent_requests = [
            req_time for req_time in self.request_history
            if current_time - req_time < 60
        ]
        
        if len(recent_requests) >= self.max_requests_per_minute:
            self.logger.warning(f"Rate limit exceeded: {len(recent_requests)} requests in last minute")
            return False
        
        # Check requests per hour
        if len(self.request_history) >= self.max_requests_per_hour:
            self.logger.warning(f"Rate limit exceeded: {len(self.request_history)} requests in last hour")
            return False
        
        return True
    
    def _get_time_since_last_request(self) -> float:
        """Get time since last request."""
        if not self.request_history:
            return float('inf')
        return time.time() - self.request_history[-1]
    
    def record_request(self, url: str) -> None:
        """Record a request for rate limiting purposes."""
        self.request_history.append(time.time())
        self.logger.debug(f"Recorded request to {url}")
    
    def calculate_required_delay(self, url: str) -> float:
        """Calculate how long to wait before next request."""
        delays = []
        
        # Minimum delay
        time_since_last = self._get_time_since_last_request()
        if time_since_last < self.min_delay:
            delays.append(self.min_delay - time_since_last)
        
        # Robots.txt crawl delay
        if self.respect_crawl_delay:
            crawl_delay = self.robots_checker.get_crawl_delay()
            if crawl_delay and time_since_last < crawl_delay:
                delays.append(crawl_delay - time_since_last)
        
        # Rate limiting delay
        current_time = time.time()
        recent_requests = [
            req_time for req_time in self.request_history
            if current_time - req_time < 60
        ]
        
        if len(recent_requests) >= self.max_requests_per_minute:
            # Wait until oldest request in the minute expires
            oldest_in_minute = min(recent_requests)
            delays.append(60 - (current_time - oldest_in_minute) + 1)
        
        return max(delays) if delays else 0
    
    def get_compliance_report(self) -> Dict[str, any]:
        """Generate a compliance report."""
        current_time = time.time()
        session_duration = current_time - self.session_start
        
        # Calculate request rates
        recent_requests = [
            req_time for req_time in self.request_history
            if current_time - req_time < 60
        ]
        
        hourly_requests = len(self.request_history)
        requests_per_minute = len(recent_requests)
        avg_requests_per_minute = len(self.request_history) / (session_duration / 60) if session_duration > 0 else 0
        
        report = {
            'session_duration_minutes': session_duration / 60,
            'total_requests': len(self.request_history),
            'requests_last_minute': requests_per_minute,
            'requests_last_hour': hourly_requests,
            'avg_requests_per_minute': avg_requests_per_minute,
            'rate_limits': {
                'max_per_minute': self.max_requests_per_minute,
                'max_per_hour': self.max_requests_per_hour,
                'within_minute_limit': requests_per_minute < self.max_requests_per_minute,
                'within_hour_limit': hourly_requests < self.max_requests_per_hour
            },
            'robots_txt': self.robots_checker.get_robots_summary(),
            'compliance_status': 'compliant' if self._check_rate_limits() else 'rate_limited'
        }
        
        return report

class TermsOfServiceChecker:
    """Checks terms of service and usage policies."""
    
    def __init__(self, base_url: str):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.terms_url = None
        self.last_check = None
        
    def find_terms_page(self) -> Optional[str]:
        """Try to find the terms of service page."""
        common_terms_paths = [
            '/terms',
            '/terms-of-service',
            '/terms-of-use',
            '/tos',
            '/legal/terms',
            '/about/terms',
            '/privacy-policy'
        ]
        
        for path in common_terms_paths:
            try:
                url = urljoin(self.base_url, path)
                response = requests.head(url, timeout=10)
                if response.status_code == 200:
                    self.terms_url = url
                    self.logger.info(f"Found terms page: {url}")
                    return url
            except:
                continue
        
        self.logger.warning("Could not find terms of service page")
        return None
    
    def check_terms_compliance(self) -> Dict[str, any]:
        """Check basic compliance with common terms."""
        compliance_items = {
            'has_terms_page': self.find_terms_page() is not None,
            'terms_url': self.terms_url,
            'recommendations': [
                "Review the website's terms of service manually",
                "Ensure scraping is for legitimate research/educational purposes",
                "Respect rate limits and don't overload the server",
                "Don't use scraped data for commercial purposes without permission",
                "Credit the source website when using scraped data"
            ],
            'best_practices': [
                "Use a descriptive User-Agent string",
                "Implement proper error handling and retries",
                "Cache responses to avoid duplicate requests",
                "Only scrape publicly available data",
                "Respect copyright and intellectual property rights"
            ]
        }
        
        return compliance_items

def run_compliance_check(base_url: str, config: Dict[str, any]) -> Dict[str, any]:
    """Run a comprehensive compliance check."""
    print("🔍 Running Compliance Check")
    print("=" * 50)
    
    # Initialize checkers
    ethical_scraper = EthicalScraper(base_url, config)
    terms_checker = TermsOfServiceChecker(base_url)
    
    # Run checks
    robots_summary = ethical_scraper.robots_checker.get_robots_summary()
    terms_compliance = terms_checker.check_terms_compliance()
    compliance_report = ethical_scraper.get_compliance_report()
    
    # Compile results
    results = {
        'timestamp': datetime.now().isoformat(),
        'base_url': base_url,
        'robots_txt': robots_summary,
        'terms_of_service': terms_compliance,
        'rate_limiting': compliance_report['rate_limits'],
        'overall_status': 'compliant'
    }
    
    # Print results
    print("\n🤖 Robots.txt Analysis:")
    if 'error' in robots_summary:
        print(f"  ❌ Error: {robots_summary['error']}")
        results['overall_status'] = 'warning'
    else:
        print(f"  ✅ Can fetch base URL: {robots_summary.get('can_fetch_base', 'Unknown')}")
        if robots_summary.get('crawl_delay'):
            print(f"  ⏱️ Crawl delay: {robots_summary['crawl_delay']} seconds")
        else:
            print(f"  ⏱️ No crawl delay specified")
    
    print("\n📜 Terms of Service:")
    if terms_compliance['has_terms_page']:
        print(f"  ✅ Terms page found: {terms_compliance['terms_url']}")
    else:
        print(f"  ⚠️ Terms page not found automatically")
    
    print("\n⚡ Rate Limiting:")
    rate_limits = compliance_report['rate_limits']
    print(f"  Max per minute: {rate_limits['max_per_minute']}")
    print(f"  Max per hour: {rate_limits['max_per_hour']}")
    print(f"  Current compliance: {'✅' if rate_limits['within_minute_limit'] and rate_limits['within_hour_limit'] else '⚠️'}")
    
    print("\n📋 Recommendations:")
    for rec in terms_compliance['recommendations']:
        print(f"  • {rec}")
    
    print("\n✅ Best Practices:")
    for practice in terms_compliance['best_practices']:
        print(f"  • {practice}")
    
    return results

def create_compliance_config() -> Dict[str, any]:
    """Create a default compliance configuration."""
    return {
        'ethical_scraping': {
            'min_delay_seconds': 1.0,
            'max_requests_per_minute': 30,
            'max_requests_per_hour': 1000,
            'respect_crawl_delay': True,
            'user_agent': 'Educational Research Bot 1.0 (respectful scraping)',
            'contact_email': 'your-email@example.com'
        },
        'robots_txt': {
            'check_interval_hours': 1,
            'fallback_on_error': True
        },
        'terms_compliance': {
            'check_manually': True,
            'purpose': 'educational_research',
            'data_usage': 'non_commercial',
            'attribution': True
        }
    }

def save_compliance_report(report: Dict[str, any], filename: str = "compliance_report.json") -> None:
    """Save compliance report to file."""
    try:
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n💾 Compliance report saved to {filename}")
    except Exception as e:
        logging.getLogger(__name__).error(f"Error saving compliance report: {e}") 