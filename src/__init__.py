"""
FunTrivia Scraper Package

A comprehensive web scraper for extracting quiz questions from FunTrivia.com
with enhanced question type detection, description extraction, and category mapping.
"""

__version__ = "2.0.0"
__author__ = "FunTrivia Scraper Team"

from .scraper.funtrivia import FunTriviaScraper
from .utils.question_classifier import QuestionClassifier
from .utils.text_processor import TextProcessor
from .utils.csv_handler import CSVHandler

__all__ = [
    'FunTriviaScraper',
    'QuestionClassifier', 
    'TextProcessor',
    'CSVHandler'
] 