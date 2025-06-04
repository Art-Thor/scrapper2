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
        """Set up comprehensive logging configuration for both file and console output."""
        logger = logging.getLogger(self.__class__.__name__)
        
        # Prevent duplicate handlers if logger already exists
        if logger.handlers:
            return logger
            
        logger.setLevel(self.config['logging']['level'])
        logger.propagate = False  # Prevent duplicate console output
        
        # Ensure log directory exists
        log_file = self.config['logging']['file']
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        
        # File handler with rotation
        try:
            from logging.handlers import RotatingFileHandler
            max_size = self.config['logging'].get('max_size', 10485760)  # 10MB default
            backup_count = self.config['logging'].get('backup_count', 5)
            
            fh = RotatingFileHandler(
                log_file, 
                maxBytes=max_size, 
                backupCount=backup_count,
                encoding='utf-8'
            )
            fh.setLevel(self.config['logging']['level'])
        except Exception as e:
            # Fallback to regular file handler
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setLevel(self.config['logging']['level'])
            print(f"Warning: Could not set up rotating file handler: {e}")
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(self.config['logging']['level'])
        
        # Enhanced formatters with more context
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        fh.setFormatter(file_formatter)
        ch.setFormatter(console_formatter)
        
        logger.addHandler(fh)
        logger.addHandler(ch)
        
        # Log the logger initialization
        logger.info(f"Logger initialized for {self.__class__.__name__}")
        logger.debug(f"Log level: {self.config['logging']['level']}")
        logger.debug(f"Log file: {log_file}")
        
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
        """
        Add random delay between requests to avoid rate limiting and detection.
        
        Uses configurable min/max delay ranges from config['scraper']['delays'].
        Defaults to 1-3 seconds if not configured.
        """
        import random
        import asyncio
        
        # Get delay configuration
        delays_config = self.config['scraper'].get('delays', {})
        min_delay = delays_config.get('min', 1.0)
        max_delay = delays_config.get('max', 3.0)
        
        # Generate random delay within the configured range
        delay = random.uniform(min_delay, max_delay)
        
        self.logger.debug(f"Adding random delay: {delay:.2f}s (range: {min_delay}-{max_delay}s)")
        await asyncio.sleep(delay)

    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the configured list."""
        import random
        return random.choice(self.config['scraper']['user_agents']) 