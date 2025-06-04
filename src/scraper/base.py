from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import logging
from playwright.async_api import Browser, Page

class BaseScraper(ABC):
    def __init__(self, config_path: str = "config/settings.json"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logger()
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        with open(config_path, 'r') as f:
            return json.load(f)

    def _setup_logger(self) -> logging.Logger:
        """Set up logging configuration."""
        logger = logging.getLogger(self.__class__.__name__)
        logger.setLevel(self.config['logging']['level'])
        
        # File handler
        fh = logging.FileHandler(self.config['logging']['file'])
        fh.setLevel(self.config['logging']['level'])
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(self.config['logging']['level'])
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
        return logger

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the scraper (e.g., launch browser)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (e.g., close browser)."""
        pass

    @abstractmethod
    async def scrape_questions(self, max_questions: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scrape questions from the website."""
        pass

    @abstractmethod
    async def download_media(self, url: str, media_type: str, question_id: str) -> str:
        """Download media (image/audio) and return the local path."""
        pass

    @abstractmethod
    def map_difficulty(self, raw_difficulty: str) -> str:
        """Map website's difficulty to standardized value."""
        pass

    @abstractmethod
    def map_domain(self, raw_domain: str) -> str:
        """Map website's domain to standardized value."""
        pass

    @abstractmethod
    def map_topic(self, raw_topic: str) -> str:
        """Map website's topic to standardized value."""
        pass

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        directories = [
            self.config['storage']['output_dir'],
            self.config['storage']['images_dir'],
            self.config['storage']['audio_dir']
        ]
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    async def _random_delay(self) -> None:
        """Add random delay between requests to avoid rate limiting."""
        import random
        import asyncio
        delay = self.config['scraper']['rate_limit']['delay_between_requests']
        jitter = random.uniform(0.5, 1.5)
        await asyncio.sleep(delay * jitter)

    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the configured list."""
        import random
        return random.choice(self.config['scraper']['user_agents']) 