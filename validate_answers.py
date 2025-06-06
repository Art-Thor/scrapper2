#!/usr/bin/env python3
"""
Script to validate question data quality and flag potential issues.
Identifies mismatches between questions, answers, and descriptions.
"""

import pandas as pd
import re
from pathlib import Path
from typing import List, Dict, Any


class QuestionValidator:
    def __init__(self):
        self.suspicious_patterns = []
        self.validation_rules = [
            self._check_name_mismatch,
            self._check_movie_mismatch,
            self._check_year_mismatch,
            self._check_answer_in_description,
            self._check_description_relevance
        ]
    
    def _check_name_mismatch(self, row: pd.Series) -> List[str]:
        """Check for name mismatches between answer and description."""
        issues = []
        question = str(row.get('Question', '')).lower()
        answer = str(row.get('CorrectAnswer', '')).lower()
        description = str(row.get('Description', '')).lower()
        
        if pd.isna(description) or not description.strip():
            return issues
        
        # Extract names from answer (assuming names are capitalized words)
        answer_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', str(row.get('CorrectAnswer', '')))
        
        # Check if description mentions different names
        for name in answer_names:
            if len(name.split()) >= 2:  # Full names only
                name_parts = name.split()
                # Check if any part of the name is in description
                name_in_desc = any(part.lower() in description for part in name_parts)
                
                if not name_in_desc:
                    # Look for other names in description
                    desc_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', str(row.get('Description', '')))
                    if desc_names and len(desc_names) > 0:
                        different_names = [n for n in desc_names if n.lower() != name.lower()]
                        if different_names:
                            issues.append(f"Name mismatch: Answer '{name}' but description mentions {different_names}")
        
        return issues
    
    def _check_movie_mismatch(self, row: pd.Series) -> List[str]:
        """Check for movie-related mismatches."""
        issues = []
        question = str(row.get('Question', '')).lower()
        answer = str(row.get('CorrectAnswer', '')).lower()
        description = str(row.get('Description', '')).lower()
        
        if 'movie' in question or 'film' in question:
            # Look for movie titles in quotes
            answer_movies = re.findall(r'"([^"]*)"', str(row.get('CorrectAnswer', '')))
            desc_movies = re.findall(r'"([^"]*)"', str(row.get('Description', '')))
            
            if answer_movies and desc_movies:
                answer_movie = answer_movies[0].lower()
                desc_movie = desc_movies[0].lower()
                
                if answer_movie != desc_movie and answer_movie not in desc_movie and desc_movie not in answer_movie:
                    issues.append(f"Movie mismatch: Answer mentions '{answer_movies[0]}' but description mentions '{desc_movies[0]}'")
        
        return issues
    
    def _check_year_mismatch(self, row: pd.Series) -> List[str]:
        """Check for year mismatches."""
        issues = []
        question = str(row.get('Question', ''))
        answer = str(row.get('CorrectAnswer', ''))
        description = str(row.get('Description', ''))
        
        # Extract years from question, answer, and description
        question_years = re.findall(r'\b(19|20)\d{2}\b', question)
        answer_years = re.findall(r'\b(19|20)\d{2}\b', answer)
        desc_years = re.findall(r'\b(19|20)\d{2}\b', description)
        
        if question_years and desc_years:
            if not any(qy in desc_years for qy in question_years):
                issues.append(f"Year mismatch: Question mentions {question_years} but description mentions {desc_years}")
        
        return issues
    
    def _check_answer_in_description(self, row: pd.Series) -> List[str]:
        """Check if the correct answer is mentioned or supported by description."""
        issues = []
        answer = str(row.get('CorrectAnswer', '')).strip()
        description = str(row.get('Description', '')).lower()
        
        if not answer or pd.isna(description) or not description.strip():
            return issues
        
        # Simple check: is any part of the answer mentioned in description?
        answer_words = answer.lower().split()
        significant_words = [w for w in answer_words if len(w) > 3 and w not in ['the', 'and', 'for', 'with']]
        
        if significant_words:
            words_in_desc = sum(1 for word in significant_words if word in description)
            if words_in_desc == 0:
                issues.append(f"Answer '{answer}' not mentioned in description")
        
        return issues
    
    def _check_description_relevance(self, row: pd.Series) -> List[str]:
        """Check if description seems relevant to the question."""
        issues = []
        question = str(row.get('Question', '')).lower()
        description = str(row.get('Description', '')).lower()
        
        if pd.isna(description) or not description.strip():
            return issues
        
        # Extract key terms from question
        question_terms = re.findall(r'\b\w{4,}\b', question)
        question_terms = [t for t in question_terms if t not in ['what', 'which', 'when', 'where', 'movie', 'film', 'name']]
        
        if question_terms:
            # Check if description mentions any key terms from question
            relevant_terms = [t for t in question_terms if t in description]
            if len(relevant_terms) == 0 and len(question_terms) > 1:
                issues.append(f"Description may not be relevant to question about {question_terms[:3]}")
        
        return issues
    
    def validate_question(self, row: pd.Series) -> Dict[str, Any]:
        """Validate a single question and return issues found."""
        all_issues = []
        
        for rule in self.validation_rules:
            try:
                issues = rule(row)
                all_issues.extend(issues)
            except Exception as e:
                all_issues.append(f"Validation error: {e}")
        
        return {
            'Key': row.get('Key', ''),
            'Question': str(row.get('Question', ''))[:100] + '...' if len(str(row.get('Question', ''))) > 100 else str(row.get('Question', '')),
            'CorrectAnswer': row.get('CorrectAnswer', ''),
            'Issues': all_issues,
            'IssueCount': len(all_issues)
        }


def validate_csv_file(csv_path: Path, max_issues_to_show: int = 10):
    """Validate questions in a CSV file."""
    if not csv_path.exists():
        print(f"📂 {csv_path.name} does not exist - skipping")
        return
    
    df = pd.read_csv(csv_path)
    if len(df) == 0:
        print(f"📄 {csv_path.name}: Empty file - skipping")
        return
    
    print(f"📄 Validating {csv_path.name}: {len(df)} questions")
    
    validator = QuestionValidator()
    validation_results = []
    
    for idx, row in df.iterrows():
        result = validator.validate_question(row)
        if result['IssueCount'] > 0:
            validation_results.append(result)
    
    # Sort by number of issues (most problematic first)
    validation_results.sort(key=lambda x: x['IssueCount'], reverse=True)
    
    if validation_results:
        print(f"  ⚠️ Found {len(validation_results)} questions with potential issues")
        
        # Show top issues
        print(f"  📋 Top {min(max_issues_to_show, len(validation_results))} most problematic questions:")
        
        for i, result in enumerate(validation_results[:max_issues_to_show], 1):
            print(f"\n    {i}. Key: {result['Key']}")
            print(f"       Q: {result['Question']}")
            print(f"       A: {result['CorrectAnswer']}")
            print(f"       Issues ({result['IssueCount']}):")
            for issue in result['Issues']:
                print(f"         • {issue}")
        
        if len(validation_results) > max_issues_to_show:
            print(f"\n    ... and {len(validation_results) - max_issues_to_show} more issues")
    else:
        print(f"  ✅ No obvious issues found")
    
    return validation_results


def main():
    """Main validation process."""
    print("🔍 Starting question validation process")
    print("=" * 50)
    print("Looking for potential data quality issues...")
    print("• Name mismatches between answers and descriptions")
    print("• Movie title mismatches")
    print("• Year inconsistencies")  
    print("• Answers not supported by descriptions")
    print("• Irrelevant descriptions")
    print()
    
    output_dir = Path("output")
    
    if not output_dir.exists():
        print(f"❌ Output directory {output_dir} does not exist")
        return
    
    csv_files = [
        "multiple_choice.csv",
        "true_false.csv",
        "sound.csv"
    ]
    
    all_issues = []
    
    for csv_file in csv_files:
        csv_path = output_dir / csv_file
        print(f"\n📁 Processing {csv_file}")
        print("-" * 30)
        
        issues = validate_csv_file(csv_path)
        if issues:
            all_issues.extend(issues)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY")
    print("=" * 50)
    
    if all_issues:
        issue_counts = {}
        for result in all_issues:
            for issue in result['Issues']:
                issue_type = issue.split(':')[0]
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        
        print(f"Total questions with issues: {len(all_issues)}")
        print(f"Issue breakdown:")
        for issue_type, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {issue_type}: {count}")
        
        print(f"\n💡 Manual review recommended for flagged questions")
        print(f"🔧 Consider implementing external validation (IMDB, Wikipedia, etc.)")
    else:
        print(f"✅ No obvious data quality issues detected")
        print(f"💡 Data appears to be relatively clean")


if __name__ == "__main__":
    main() 