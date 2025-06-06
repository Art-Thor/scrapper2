#!/usr/bin/env python3

import re
from typing import Dict, List, Any, Optional

def _split_page_text_by_questions(page_text: str) -> Dict[str, str]:
    sections = {}
    question_pattern = r'(\d+)\.\s+'
    matches = list(re.finditer(question_pattern, page_text, re.MULTILINE | re.IGNORECASE))
    
    print(f'Found {len(matches)} question patterns')
    for match in matches:
        print(f'  Match: \'{match.group()}\' at position {match.start()}')
    
    for i, match in enumerate(matches):
        question_num = match.group(1)
        if not question_num:
            continue
        
        start_pos = match.start()
        if i + 1 < len(matches):
            end_pos = matches[i + 1].start()
        else:
            end_pos = len(page_text)
        
        section_text = page_text[start_pos:end_pos].strip()
        sections[question_num] = section_text
        print(f'Question {question_num} section: {len(section_text)} characters')
        
    return sections

sample_text = '''
7. In the Roman Catholic Church, the Easter Vigil is held late in the day on Holy Saturday. The rubrics of the Mass call for the faithful to do something they have not done at any services since the beginning of Lent. What is this?

❌ Your Answer: [No Answer]

The correct answer was Use the word "Alleluia"

"Alleluia" is a term considered appropriate to celebrations of the risen Christ, and therefore not said during Lent. The Easter Vigil customarily lasts about three hours. In many areas, it is held so as to run from late Saturday night until early Easter Sunday morning. It is also the service at which new converts are received into the church, through Baptism and/or Confirmation.

55% of players have answered correctly.

8. In the Muslim faith, what is al-Jumuah?

❌ Your Answer: [No Answer]

The correct answer was Friday prayer

This is held at a mosque (masjid). Al-Jumuah is observed at noon.

44% of players have answered correctly.

9. In the Hindu faith, during what time of day is the Nitya Puja service performed?

❌ Your Answer: [No Answer]

The correct answer was Morning

The puja may be accompanied by Kirtan or Dhun music. One may also sit on a mat, called an asan.
'''

print("🔧 Testing correct answer extraction")
print("=" * 50)

sections = _split_page_text_by_questions(sample_text)
if '8' in sections:
    section_text = sections['8']
    print(f'\nSection for Q8:')
    print(section_text)
    
    pattern = r'The correct answer was\s+([^.\n\r]+)'
    matches = re.findall(pattern, section_text, re.IGNORECASE | re.DOTALL)
    print(f'\nMatches found: {matches}')
    
    if matches:
        answer_text = matches[0].strip()
        print(f'Answer text: "{answer_text}"')
        
        test_options = ['Prayer before meals', 'The naming of a child', 'Friday prayer', 'Prayer for the sick']
        print(f'Test options: {test_options}')
        
        for option in test_options:
            if option.lower() == answer_text.lower():
                print(f'✅ EXACT MATCH: {option}')
                break
        else:
            print(f'❌ No exact match found')
            print(f'Checking partial matches...')
            for option in test_options:
                if option.lower() in answer_text.lower() or answer_text.lower() in option.lower():
                    print(f'✅ PARTIAL MATCH: {option}')
                    break
            else:
                print(f'❌ No partial match found either')
else:
    print('❌ No section found for Q8')
    print(f'Available sections: {list(sections.keys())}') 