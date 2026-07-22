import re
from typing import Optional

# Characters Slack clients wrap around text when a user applies bold/italic/
# strikethrough/code formatting. They arrive verbatim in the event payload.
_MARKDOWN_WRAPPERS = "*_`~"

# Commands that end a workday
END_COMMANDS = {"\\end", "\\\\end", "\\stop", "\\\\stop", "end", "stop", "logout", "\\logout"}


class SlackMessageValidator:
    """
    Validates Slack messages for daily start reports and end-of-day logout reports.

    Start Report Example:
    July 13, 2026 - Start

    Tasks:
    • Task A
    • Task B

    Expected Today:
    • Goal A
    • Goal B

    End Report Example:
    July 13, 2026 - End (or Complete / Summary / Done)

    Completed Tasks:
    • Task A - Done
    • Task B - Done
    """

    # Start report patterns
    START_PATTERN = re.compile(r".* - Start", re.IGNORECASE)
    TASKS_PATTERN = re.compile(r"Tasks:", re.IGNORECASE)
    EXPECTED_PATTERN = re.compile(r"Expected Today:", re.IGNORECASE)

    # End report patterns
    END_HEADER_PATTERN = re.compile(
        r"(.* - (End|Complete|Completed|Done|Stop|Summary|Finish|Finished|Evening)|end of day|evening report|daily end)",
        re.IGNORECASE
    )
    COMPLETED_TASKS_PATTERN = re.compile(
        r"(Completed Tasks|Tasks Completed|Completed|Tasks Done|Tasks Finished|Summary):",
        re.IGNORECASE
    )

    @staticmethod
    def normalize(text: Optional[str]) -> str:
        """
        Strips surrounding whitespace and Slack markdown wrappers so formatting doesn't defeat matching.
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

        # Check for all required components of a start report
        has_start = bool(cls.START_PATTERN.search(normalized))
        has_tasks = bool(cls.TASKS_PATTERN.search(normalized))
        has_expected = bool(cls.EXPECTED_PATTERN.search(normalized))

        return has_start and has_tasks and has_expected

    @classmethod
    def is_valid_end_report(cls, text: Optional[str]) -> bool:
        normalized = cls.normalize(text)
        if not normalized:
            return False

        # If it's a start report, it's not an end report
        if cls.is_valid_start_report(text):
            return False

        has_end_header = bool(cls.END_HEADER_PATTERN.search(normalized))
        has_completed_tasks = bool(cls.COMPLETED_TASKS_PATTERN.search(normalized))

        return has_end_header or has_completed_tasks
