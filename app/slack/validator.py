import re
from typing import Optional

class SlackMessageValidator:
    """
    Validates Slack messages for daily start reports.
    Example:
    July 13, 2026 - Start
    
    Tasks:
    • Task A
    • Task B
    
    Expected Today:
    • Goal A
    • Goal B
    """
    
    # Pattern to match the date and "Start" keyword
    START_PATTERN = re.compile(r".* - Start", re.IGNORECASE)
    
    # Pattern to match "Tasks:" section
    TASKS_PATTERN = re.compile(r"Tasks:", re.IGNORECASE)
    
    # Pattern to match "Expected Today:" section
    EXPECTED_PATTERN = re.compile(r"Expected Today:", re.IGNORECASE)
    
    @classmethod
    def is_valid_start_report(cls, text: str) -> bool:
        if not text:
            return False
            
        # Check for all required components
        has_start = bool(cls.START_PATTERN.search(text))
        has_tasks = bool(cls.TASKS_PATTERN.search(text))
        has_expected = bool(cls.EXPECTED_PATTERN.search(text))
        
        return has_start and has_tasks and has_expected
