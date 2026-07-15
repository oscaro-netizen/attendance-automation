import pytest
from app.slack.validator import SlackMessageValidator

@pytest.mark.parametrize("message_text, expected_validity", [
    ("July 13, 2026 - Start\n\nTasks:\n• Task A\n\nExpected Today:\n• Goal A", True),
    ("July 13, 2026 - Start\nTasks:\n• Task A\nExpected Today:\n• Goal A", True),
    ("July 13, 2026 - Start\n\nTasks:\n• Task A", False), # Missing Expected Today
    ("Tasks:\n• Task A\n\nExpected Today:\n• Goal A", False), # Missing Start
    ("July 13, 2026 - Start\n\nExpected Today:\n• Goal A", False), # Missing Tasks
    ("Just a random message", False),
    ("", False),
    (None, False),
])
def test_is_valid_start_report(message_text, expected_validity):
    assert SlackMessageValidator.is_valid_start_report(message_text) == expected_validity
