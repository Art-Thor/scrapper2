"""
Scraper modules for different quiz websites.

This package contains scraper implementations for various quiz platforms,
with the main focus on FunTrivia.com.
"""

from .funtrivia import FunTriviaScraper
from .base import BaseScraper

__all__ = [
    'FunTriviaScraper',
    'BaseScraper'
] 