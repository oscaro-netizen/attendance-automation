import re
from typing import Optional

# Characters Slack clients wrap around text when a user applies bold/italic/
# strikethrough/code formatting. They arrive verbatim in the event payload and
# would otherwise defeat exact-match command parsing.
_MARKDOWN_WRAPPERS = "*_`~"

# The command that ends a workday, in the forms Slack may deliver it: a plain
# backslash command, or an escaped one if the client escapes the backslash.
END_COMMANDS = {"\\end", "\\\\end"}


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

    @staticmethod
    def normalize(text: Optional[str]) -> str:
        """
        Strips surrounding whitespace and Slack markdown wrappers so that
        `*\\end*` and `\\end` are treated identically.
        """
        if not text:
            return ""
        return text.strip().strip(_MARKDOWN_WRAPPERS).strip()

    @classmethod
    def is_end_command(cls, text: Optional[str]) -> bool:
        return cls.normalize(text).lower() in END_COMMANDS

    @classmethod
    def is_valid_start_report(cls, text: Optional[str]) -> bool:
        normalized = cls.normalize(text)
        if not normalized:
            return False

        # Check for all required components
        has_start = bool(cls.START_PATTERN.search(normalized))
        has_tasks = bool(cls.TASKS_PATTERN.search(normalized))
        has_expected = bool(cls.EXPECTED_PATTERN.search(normalized))

        return has_start and has_tasks and has_expected
