import pandas as pd
import re
import os
from typing import Dict, List, Any, Tuple, Optional, Set
import logging
from pathlib import Path

class DataValidator:
    """Comprehensive data validation for scraped questions."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.validation_errors = []
        self.validation_warnings = []
    
    def validate_question_data(self, question: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
        """Validate a single question's data structure and content."""
        errors = []
        warnings = []
        
        # Required fields validation
        required_fields = ['id', 'type', 'question', 'options', 'domain', 'topic', 'difficulty']
        for field in required_fields:
            if field not in question or not question[field]:
                errors.append(f"Missing or empty required field: {field}")
        
        # Question ID format validation
        if 'id' in question:
            if not self._validate_question_id(question['id']):
                errors.append(f"Invalid question ID format: {question['id']}")
        
        # Question type validation
        if 'type' in question:
            valid_types = ['multiple_choice', 'true_false', 'sound']
            if question['type'] not in valid_types:
                errors.append(f"Invalid question type: {question['type']} (must be one of {valid_types})")
        
        # Question text validation
        if 'question' in question:
            question_errors, question_warnings = self._validate_question_text(question['question'])
            errors.extend(question_errors)
            warnings.extend(question_warnings)
        
        # Options validation
        if 'options' in question and 'type' in question:
            option_errors, option_warnings = self._validate_options(question['options'], question['type'])
            errors.extend(option_errors)
            warnings.extend(option_warnings)
        
        # Correct answer validation
        if 'correct_answer' in question and 'options' in question:
            answer_errors = self._validate_correct_answer(question['correct_answer'], question['options'])
            errors.extend(answer_errors)
        
        # Domain and topic validation
        domain_errors = self._validate_domain_topic(question.get('domain'), question.get('topic'))
        errors.extend(domain_errors)
        
        # Difficulty validation
        if 'difficulty' in question:
            if not self._validate_difficulty(question['difficulty']):
                errors.append(f"Invalid difficulty level: {question['difficulty']}")
        
        # Media path validation
        if 'media_path' in question and question['media_path']:
            media_errors, media_warnings = self._validate_media_path(question['media_path'], question.get('type'))
            errors.extend(media_errors)
            warnings.extend(media_warnings)
        
        # Hint validation
        if 'hint' in question and question['hint']:
            hint_warnings = self._validate_hint(question['hint'])
            warnings.extend(hint_warnings)
        
        is_valid = len(errors) == 0
        return is_valid, errors, warnings
    
    def _validate_question_id(self, question_id: str) -> bool:
        """
        Validate question ID format using the new localization key pattern.
        
        Expected format: Question_{TYPE}_Parsed_{DOMAIN}_{DIFFICULTY}_{UNIQUEID}
        Examples:
        - Question_MQ_Parsed_Culture_Normal_0001
        - Question_TF_Parsed_Science_Hard_0001
        - Question_Sound_Parsed_Nature_Easy_0001
        """
        # Updated pattern to match new localization key format with domain and difficulty
        pattern = r'^Question_(MQ|TF|Sound)_Parsed_[A-Za-z]+_[A-Za-z]+_\d{4}$'
        return bool(re.match(pattern, question_id))
    
    def _validate_question_text(self, question_text: str) -> Tuple[List[str], List[str]]:
        """Validate question text content."""
        errors = []
        warnings = []
        
        if not question_text or not question_text.strip():
            errors.append("Question text is empty")
            return errors, warnings
        
        # Length validation
        if len(question_text.strip()) < 10:
            warnings.append("Question text is very short (less than 10 characters)")
        elif len(question_text) > 500:
            warnings.append("Question text is very long (more than 500 characters)")
        
        # Check for common issues
        if question_text.strip().endswith('?') == False and 'true' not in question_text.lower() and 'false' not in question_text.lower():
            warnings.append("Question doesn't end with '?' and doesn't appear to be a statement")
        
        # Check for HTML remnants
        if '<' in question_text or '>' in question_text:
            warnings.append("Question text may contain HTML tags")
        
        # Check for encoding issues
        if '&quot;' in question_text or '&amp;' in question_text or '&#' in question_text:
            warnings.append("Question text may contain HTML entities")
        
        return errors, warnings
    
    def _validate_options(self, options: List[str], question_type: str) -> Tuple[List[str], List[str]]:
        """Validate answer options based on question type."""
        errors = []
        warnings = []
        
        if not isinstance(options, list):
            errors.append("Options must be a list")
            return errors, warnings
        
        # Type-specific validation
        if question_type == 'true_false':
            if len(options) != 2:
                errors.append(f"True/False questions must have exactly 2 options, got {len(options)}")
            else:
                valid_options = {'true', 'false', 'yes', 'no'}
                for option in options:
                    if option.lower().strip() not in valid_options:
                        warnings.append(f"Unusual True/False option: {option}")
        
        elif question_type == 'multiple_choice':
            if len(options) < 2:
                errors.append(f"Multiple choice questions must have at least 2 options, got {len(options)}")
            elif len(options) > 6:
                warnings.append(f"Multiple choice question has many options ({len(options)})")
        
        elif question_type == 'sound':
            if len(options) < 2:
                errors.append(f"Sound questions must have at least 2 options, got {len(options)}")
        
        # Validate individual options
        for i, option in enumerate(options):
            if not option or not option.strip():
                errors.append(f"Option {i+1} is empty")
            elif len(option.strip()) < 1:
                errors.append(f"Option {i+1} is too short")
            elif len(option) > 200:
                warnings.append(f"Option {i+1} is very long ({len(option)} characters)")
        
        # Check for duplicate options
        clean_options = [opt.strip().lower() for opt in options if opt.strip()]
        if len(clean_options) != len(set(clean_options)):
            errors.append("Duplicate options found")
        
        return errors, warnings
    
    def _validate_correct_answer(self, correct_answer: str, options: List[str]) -> List[str]:
        """Validate that correct answer matches one of the options."""
        errors = []
        
        if not correct_answer or not correct_answer.strip():
            errors.append("Correct answer is empty")
            return errors
        
        # Check if correct answer matches any option
        clean_answer = correct_answer.strip().lower()
        clean_options = [opt.strip().lower() for opt in options if opt.strip()]
        
        # Exact match check
        if clean_answer not in clean_options:
            # Partial match check
            partial_matches = [opt for opt in clean_options if clean_answer in opt or opt in clean_answer]
            if not partial_matches:
                errors.append(f"Correct answer '{correct_answer}' doesn't match any option: {options}")
        
        return errors
    
    def _validate_domain_topic(self, domain: str, topic: str) -> List[str]:
        """Validate domain and topic values."""
        errors = []
        
        valid_domains = ['Nature', 'Science', 'Geography', 'Culture', 'Sports', 'History']
        valid_difficulties = ['Easy', 'Normal', 'Hard']
        
        if not domain:
            errors.append("Domain is missing")
        elif domain not in valid_domains:
            # This is just a warning since mappings might create new domains
            pass
        
        if not topic:
            errors.append("Topic is missing")
        
        return errors
    
    def _validate_difficulty(self, difficulty: str) -> bool:
        """Validate difficulty level."""
        valid_difficulties = ['Easy', 'Normal', 'Hard']
        return difficulty in valid_difficulties
    
    def _validate_media_path(self, media_path: str, question_type: str) -> Tuple[List[str], List[str]]:
        """Validate media file path."""
        errors = []
        warnings = []
        
        if not media_path.strip():
            warnings.append("Empty media path")
            return errors, warnings
        
        # Check path format
        if not media_path.startswith('assets/'):
            warnings.append(f"Media path doesn't start with 'assets/': {media_path}")
        
        # Check file extension
        valid_image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        valid_audio_extensions = {'.mp3', '.wav', '.ogg', '.m4a'}
        
        _, ext = os.path.splitext(media_path.lower())
        
        if question_type == 'sound':
            if ext not in valid_audio_extensions:
                warnings.append(f"Unusual audio file extension: {ext}")
            if 'images' in media_path:
                errors.append("Sound question has image path")
        else:
            if ext not in valid_image_extensions:
                warnings.append(f"Unusual image file extension: {ext}")
            if 'audio' in media_path:
                errors.append("Non-sound question has audio path")
        
        return errors, warnings
    
    def _validate_hint(self, hint: str) -> List[str]:
        """Validate hint content."""
        warnings = []
        
        if len(hint.strip()) < 5:
            warnings.append("Hint is very short")
        elif len(hint) > 1000:
            warnings.append("Hint is very long")
        
        # Check for HTML remnants
        if '<' in hint or '>' in hint:
            warnings.append("Hint may contain HTML tags")
        
        return warnings

class CSVTemplateValidator:
    """Validates CSV output against expected templates."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_csv_structure(self, csv_file: str, question_type: str) -> Tuple[bool, List[str]]:
        """Validate CSV file structure against template."""
        errors = []
        
        if not os.path.exists(csv_file):
            errors.append(f"CSV file not found: {csv_file}")
            return False, errors
        
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            errors.append(f"Error reading CSV file: {e}")
            return False, errors
        
        # Get expected columns for question type
        expected_columns = self._get_expected_columns(question_type)
        
        # Check column presence
        missing_columns = set(expected_columns) - set(df.columns)
        if missing_columns:
            errors.append(f"Missing columns: {missing_columns}")
        
        # Check for extra columns
        extra_columns = set(df.columns) - set(expected_columns)
        if extra_columns:
            self.logger.warning(f"Extra columns found: {extra_columns}")
        
        # Check column order
        present_expected_cols = [col for col in expected_columns if col in df.columns]
        present_actual_cols = [col for col in df.columns if col in expected_columns]
        
        if present_expected_cols != present_actual_cols:
            errors.append("Column order doesn't match template")
        
        # Validate data content
        content_errors = self._validate_csv_content(df, question_type)
        errors.extend(content_errors)
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def _get_expected_columns(self, question_type: str) -> List[str]:
        """Get expected column structure for question type."""
        templates = {
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
        
        return templates.get(question_type, templates['multiple_choice'])
    
    def _validate_csv_content(self, df: pd.DataFrame, question_type: str) -> List[str]:
        """Validate CSV content for consistency."""
        errors = []
        
        if df.empty:
            errors.append("CSV file is empty")
            return errors
        
        # Check for duplicate keys
        if 'Key' in df.columns:
            duplicate_keys = df[df['Key'].duplicated()]['Key'].tolist()
            if duplicate_keys:
                errors.append(f"Duplicate question keys found: {duplicate_keys[:5]}...")
        
        # Check for empty required fields
        required_fields = ['Key', 'Question', 'CorrectAnswer']
        for field in required_fields:
            if field in df.columns:
                empty_count = df[field].isna().sum() + (df[field] == '').sum()
                if empty_count > 0:
                    errors.append(f"{empty_count} rows have empty {field}")
        
        # Type-specific validation
        if question_type == 'true_false':
            # Check that options are True/False
            if 'Option1' in df.columns and 'Option2' in df.columns:
                valid_tf_options = {'True', 'False', 'true', 'false', 'Yes', 'No', 'yes', 'no'}
                for idx, row in df.iterrows():
                    opt1, opt2 = str(row.get('Option1', '')), str(row.get('Option2', ''))
                    if opt1 not in valid_tf_options or opt2 not in valid_tf_options:
                        errors.append(f"Row {idx+1}: Invalid True/False options: {opt1}, {opt2}")
                        break  # Don't spam with too many errors
        
        return errors

def validate_scraped_data(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate a batch of scraped questions and return summary."""
    validator = DataValidator()
    
    validation_summary = {
        'total_questions': len(questions),
        'valid_questions': 0,
        'invalid_questions': 0,
        'questions_with_warnings': 0,
        'errors': [],
        'warnings': [],
        'error_types': {},
        'warning_types': {}
    }
    
    for i, question in enumerate(questions):
        is_valid, errors, warnings = validator.validate_question_data(question)
        
        if is_valid:
            validation_summary['valid_questions'] += 1
        else:
            validation_summary['invalid_questions'] += 1
            validation_summary['errors'].extend([f"Question {i+1}: {error}" for error in errors])
        
        if warnings:
            validation_summary['questions_with_warnings'] += 1
            validation_summary['warnings'].extend([f"Question {i+1}: {warning}" for warning in warnings])
        
        # Count error and warning types
        for error in errors:
            error_type = error.split(':')[0] if ':' in error else error
            validation_summary['error_types'][error_type] = validation_summary['error_types'].get(error_type, 0) + 1
        
        for warning in warnings:
            warning_type = warning.split(':')[0] if ':' in warning else warning
            validation_summary['warning_types'][warning_type] = validation_summary['warning_types'].get(warning_type, 0) + 1
    
    return validation_summary

def print_validation_report(validation_summary: Dict[str, Any]) -> None:
    """Print a formatted validation report."""
    print("\n📊 Data Validation Report")
    print("=" * 50)
    print(f"Total Questions: {validation_summary['total_questions']}")
    print(f"Valid Questions: {validation_summary['valid_questions']}")
    print(f"Invalid Questions: {validation_summary['invalid_questions']}")
    print(f"Questions with Warnings: {validation_summary['questions_with_warnings']}")
    
    if validation_summary['error_types']:
        print("\n❌ Error Types:")
        for error_type, count in validation_summary['error_types'].items():
            print(f"  {error_type}: {count}")
    
    if validation_summary['warning_types']:
        print("\n⚠️ Warning Types:")
        for warning_type, count in validation_summary['warning_types'].items():
            print(f"  {warning_type}: {count}")
    
    if validation_summary['errors']:
        print(f"\n❌ First 5 Errors:")
        for error in validation_summary['errors'][:5]:
            print(f"  {error}")
    
    if validation_summary['warnings']:
        print(f"\n⚠️ First 5 Warnings:")
        for warning in validation_summary['warnings'][:5]:
            print(f"  {warning}")

def validate_csv_files(output_dir: str, csv_files: Dict[str, str]) -> Dict[str, bool]:
    """Validate all CSV files against their templates."""
    validator = CSVTemplateValidator()
    results = {}
    
    print("\n🔍 Validating CSV Files")
    print("-" * 30)
    
    for question_type, csv_filename in csv_files.items():
        csv_path = os.path.join(output_dir, csv_filename)
        is_valid, errors = validator.validate_csv_structure(csv_path, question_type)
        
        results[question_type] = is_valid
        
        if is_valid:
            print(f"✅ {question_type}: Valid")
        else:
            print(f"❌ {question_type}: Invalid")
            for error in errors:
                print(f"   {error}")
    
    return results 