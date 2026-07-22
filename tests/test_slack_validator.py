import pytest

from app.slack.validator import SlackMessageValidator
from tests.factories import VALID_START_REPORT


class TestStartReport:
    def test_accepts_a_well_formed_report(self):
        assert SlackMessageValidator.is_valid_start_report(VALID_START_REPORT)

    def test_accepts_a_report_wrapped_in_slack_markdown(self):
        assert SlackMessageValidator.is_valid_start_report(f"*{VALID_START_REPORT}*")

    @pytest.mark.parametrize(
        "text",
        [
            "",
            None,
            "   ",
            "July 13, 2026 - Start",                       # no Tasks / Expected sections
            "Tasks:\n• A\n\nExpected Today:\n• B",         # no Start line
            "July 13, 2026 - Start\n\nTasks:\n• A",        # no Expected Today section
            "just chatting in the channel",
        ],
    )
    def test_rejects_anything_missing_a_required_section(self, text):
        assert not SlackMessageValidator.is_valid_start_report(text)


class TestEndCommand:
    @pytest.mark.parametrize("text", ["\\end", "  \\end  ", "*\\end*", "`\\end`", "\\END"])
    def test_accepts_the_end_command_in_the_forms_slack_delivers_it(self, text):
        assert SlackMessageValidator.is_end_command(text)

    @pytest.mark.parametrize("text", ["end", "\\ended", "\\stop", "please \\end", "", None])
    def test_rejects_near_misses(self, text):
        assert not SlackMessageValidator.is_end_command(text)

    def test_a_start_report_is_not_an_end_command(self):
        assert not SlackMessageValidator.is_end_command(VALID_START_REPORT)


class TestNormalize:
    def test_strips_whitespace_and_markdown_wrappers(self):
        assert SlackMessageValidator.normalize("  *~hello~*  ") == "hello"

    def test_normalizes_missing_text_to_empty_string(self):
        assert SlackMessageValidator.normalize(None) == ""
