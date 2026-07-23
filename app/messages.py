"""
Deciding what a Slack message means.

Only two kinds of message do anything:

    a daily start report      -> clock in
    a completed-work report   -> clock out

Everything else is ordinary conversation and is ignored.
"""
import re
from enum import Enum
from typing import Optional

# Slack delivers the characters the user typed, including the wrappers its
# clients add for bold/italic/strikethrough/code. `*Completed Work:*` must behave
# exactly like `Completed Work:`, so these are stripped before matching.
_MARKDOWN_WRAPPERS = "*_`~"

# An end-of-day report ends the day:
#
#     July 23, 2026 - End
#
#     Completed Tasks:
#     • Invoice export - Done
#
# Either marker on its own is enough: people write the header without the
# section, or the section without the header. Both are anchored to the start of
# a line so that "we'll review completed tasks tomorrow" in ordinary chat does
# not clock anyone out.
_END_HEADER = re.compile(
    r"^\s*(.* - (End|Complete|Completed|Done|Stop|Summary|Finish|Finished|Evening)"
    r"|End of Day|Evening Report|Daily End)\b",
    re.IGNORECASE | re.MULTILINE,
)
_COMPLETED_TASKS = re.compile(
    r"^\s*(Completed Tasks|Tasks Completed|Completed|Tasks Done|Tasks Finished|Summary)\s*:",
    re.IGNORECASE | re.MULTILINE,
)

# A start report looks like:
#
#     July 23, 2026 - Start
#
#     Tasks:
#     • Finish the invoice export
#
#     Expected Today:
#     • Invoice export merged
#
# All three markers must be present; any one alone is likely ordinary chat.
_START_MARKER = re.compile(r".* - Start", re.IGNORECASE)
_TASKS_MARKER = re.compile(r"Tasks:", re.IGNORECASE)
_EXPECTED_MARKER = re.compile(r"Expected Today:", re.IGNORECASE)


class Action(str, Enum):
    CLOCK_IN = "clock_in"
    CLOCK_OUT = "clock_out"


def normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    return text.strip().strip(_MARKDOWN_WRAPPERS).strip()


def classify(text: Optional[str]) -> Optional[Action]:
    """Returns the action a message asks for, or None if it asks for nothing."""
    normalized = normalize(text)
    if not normalized:
        return None

    # A start report is checked first: it is the stricter pattern (three markers,
    # all required), so anything matching it is unambiguously a start.
    if (
        _START_MARKER.search(normalized)
        and _TASKS_MARKER.search(normalized)
        and _EXPECTED_MARKER.search(normalized)
    ):
        return Action.CLOCK_IN

    if _END_HEADER.search(normalized) or _COMPLETED_TASKS.search(normalized):
        return Action.CLOCK_OUT

    return None
