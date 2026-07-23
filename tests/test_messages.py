"""What counts as a command, and -- more importantly -- what does not."""
import pytest

from app.messages import Action, classify

START_REPORT = """July 23, 2026 - Start

Tasks:
• Finish the invoice export

Expected Today:
• Invoice export merged
"""


def test_a_full_start_report_clocks_in():
    assert classify(START_REPORT) is Action.CLOCK_IN


END_REPORT = """July 23, 2026 - End

Completed Tasks:
• Invoice export - Done
• Ada's pull request - Done
"""


def test_a_full_end_report_clocks_out():
    assert classify(END_REPORT) is Action.CLOCK_OUT


@pytest.mark.parametrize(
    "text",
    [
        "July 23, 2026 - End",              # header alone
        "July 23, 2026 - Complete",
        "July 23, 2026 - Done",
        "July 23, 2026 - Summary",
        "End of Day",
        "Evening Report",
        "Completed Tasks:\n• a",            # section alone, no header
        "Tasks Completed:\n• a",
        "Tasks Done:\n• a",
        "completed tasks:\n• a",            # lower case
        "  Completed Tasks:\n• a",          # leading whitespace
    ],
)
def test_end_reports_are_recognised_in_their_documented_forms(text):
    assert classify(text) is Action.CLOCK_OUT


def test_markdown_wrapped_end_report_still_clocks_out():
    """Slack sends formatting characters verbatim; bolding must not break it."""
    assert classify("*Completed Tasks:*\n• a") is Action.CLOCK_OUT


def test_a_start_report_is_never_mistaken_for_an_end_report():
    """The start report contains 'Tasks:', which must not match the end patterns."""
    assert classify(START_REPORT) is Action.CLOCK_IN


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "   ",
        "good morning everyone",
        "July 23, 2026 - Start",  # missing Tasks: and Expected Today:
        "Tasks:\n• something",  # missing the start line
        "July 23, 2026 - Start\n\nTasks:\n• a",  # missing Expected Today:
        "we should review completed tasks tomorrow",  # marker not at line start
        "I am done for now",
    ],
)
def test_ordinary_messages_are_ignored(text):
    assert classify(text) is None


def test_start_report_is_case_insensitive():
    assert classify(START_REPORT.replace("Start", "start").replace("Tasks", "TASKS")) is Action.CLOCK_IN
