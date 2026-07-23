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


COMPLETED_REPORT = """July 23, 2026 - End

Completed Work:
• Invoice export merged
• Reviewed Ada's pull request
"""


def test_a_completed_work_report_clocks_out():
    assert classify(COMPLETED_REPORT) is Action.CLOCK_OUT


@pytest.mark.parametrize(
    "text",
    [
        "Completed Work:\n• a",           # no date line above it
        "completed work:\n• a",           # lower case
        "COMPLETED WORK\n• a",            # upper case, no colon
        "Completed  Work:\n• a",          # extra space
        "  Completed Work:\n• a",         # leading whitespace
    ],
)
def test_completed_work_is_recognised_in_its_common_forms(text):
    assert classify(text) is Action.CLOCK_OUT


def test_markdown_wrapped_completed_report_still_clocks_out():
    """Slack sends formatting characters verbatim; bolding must not break it."""
    assert classify("*Completed Work:*\n• a") is Action.CLOCK_OUT


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
        "I completed work on the export today",  # marker not at the start of a line
        "we should discuss completed work tomorrow",
    ],
)
def test_ordinary_messages_are_ignored(text):
    assert classify(text) is None


def test_start_report_is_case_insensitive():
    assert classify(START_REPORT.replace("Start", "start").replace("Tasks", "TASKS")) is Action.CLOCK_IN
