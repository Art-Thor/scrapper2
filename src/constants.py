"""
Constants and configuration values for the FunTrivia scraper.

This module centralizes all magic numbers, patterns, and reusable constants
to improve maintainability and reduce code duplication.
"""

# Question Type Detection Constants
TRUE_FALSE_SYNONYMS = {
    'true': ['true', 't', 'yes', 'y', 'correct', 'right', 'agree'],
    'false': ['false', 'f', 'no', 'n', 'incorrect', 'wrong', 'disagree']
}

TRUE_FALSE_PATTERNS = [
    ('true', 'false'), ('yes', 'no'), ('y', 'n'), ('t', 'f'),
    ('correct', 'incorrect'), ('right', 'wrong'), ('agree', 'disagree')
]

QUESTION_PATTERNS = {
    'true_false_indicators': [
        r'\bis\s+it\b', r'\bdoes\b', r'\bcan\b', r'\bwill\b', r'\bwere\b',
        r'\bhas\b', r'\bhave\b', r'\bare\b', r'\bam\b', r'\bdo\b', r'\bdid\b',
        r'\btrue\s+or\s+false\b', r'\byes\s+or\s+no\b', r'\bcorrect\s+or\s+incorrect\b'
    ],
    'factual_indicators': [
        r'\bwhat\s+year\b', r'\bwhich\s+year\b', r'\bwhen\s+was\b', r'\bwhen\s+did\b',
        r'\bwho\s+was\b', r'\bwhere\s+was\b', r'\bwhat\s+is\s+the\b', r'\bwhich\s+is\s+the\b'
    ],
    'sound_indicators': ['sound', 'audio', 'listen']
}

# Scraping Configuration Constants
TIMEOUTS = {
    'page_load': 60000,
    'network_idle': 45000,
    'quiz_page': 45000,
    'quiz_wait': 30000,
    'results_wait': 30000
}

RATE_LIMITS = {
    'requests_per_minute': 15,
    'delay_between_requests': 4,
    'random_delay_min': 1,
    'random_delay_max': 3
}

# Text Processing Constants
TEXT_CLEANUP_PATTERNS = {
    'question_prefixes': [r'^\d+\.\s*'],
    'hint_prefixes': ['Explanation:', 'Hint:'],
    'description_prefixes': ['Explanation:', 'Description:', 'Summary:', 'Interesting Information:', 'Fun Fact:']
}

# CSS Selectors for Description Extraction
DESCRIPTION_SELECTORS = [
    '.question-explanation',
    '.question-summary', 
    '.explanation',
    '.answer-explanation',
    '.question-info',
    '.trivia-fact',
    '.additional-info'
]

# Question Type Thresholds
THRESHOLDS = {
    'short_option_length': 10,
    'medium_option_length': 15,
    'similarity_threshold': 0.3,
    'min_description_length': 10,
    'min_explanation_length': 30,
    'max_question_length': 500,
    'min_question_length': 10
}

# File Paths and Names
DEFAULT_PATHS = {
    'config_file': 'config/settings.json',
    'mappings_file': 'config/mappings.json',
    'indices_file': 'question_indices.json',
    'logs_dir': 'logs',
    'output_dir': 'output',
    'assets_dir': 'assets'
}

# CSV Column Structures
CSV_COLUMNS = {
    'multiple_choice': [
        'Key', 'Domain', 'Topic', 'Difficulty', 'Question',
        'Option1', 'Option2', 'Option3', 'Option4', 
        'CorrectAnswer', 'Hint', 'Description', 'ImagePath'
    ],
    'true_false': [
        'Key', 'Domain', 'Topic', 'Difficulty', 'Question',
        'Option1', 'Option2', 'CorrectAnswer', 'Hint', 'Description'
    ],
    'sound': [
        'Key', 'Domain', 'Topic', 'Difficulty', 'Question',
        'Option1', 'Option2', 'Option3', 'Option4',
        'CorrectAnswer', 'Hint', 'Description', 'AudioPath'
    ]
}

# User Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"
]

# Category Collection Constants
CATEGORY_COLLECTION = {
    'max_samples': 25,
    'progress_save_interval': 5,
    'max_retries': 3,
    'timeout_seconds': 60
} 