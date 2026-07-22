"""Routing decisions made by `SlackEventService` before anything is queued."""
import pytest

from app.core.config import settings
from app.schemas.slack_schemas import SlackEventEnvelope
from app.services import slack_event_service as ses
from app.services.slack_event_service import (
    SlackEventOutcome,
    SlackEventQueueError,
    SlackEventService,
)
from tests.factories import (
    VALID_START_REPORT,
    FakeDeduplicator,
    FakeSlackClient,
    FakeTask,
    message_event,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def tasks(monkeypatch):
    """Replaces both Celery task handles and returns them for assertions."""
    start, end = FakeTask("task-start"), FakeTask("task-end")
    monkeypatch.setattr(ses, "process_attendance_task", start)
    monkeypatch.setattr(ses, "process_logout_task", end)
    return {"start": start, "end": end}


@pytest.fixture
def slack():
    return FakeSlackClient()


def build_service(db_session, slack, duplicate=False):
    return SlackEventService(
        db=db_session,
        deduplicator=FakeDeduplicator(duplicate=duplicate),
        slack_client=slack,
    )


async def process(service, payload):
    return await service.process_event(SlackEventEnvelope.model_validate(payload), request_id="req-1")


class TestQueueing:
    async def test_a_valid_start_report_queues_the_attendance_task(
        self, db_session, employee, slack, tasks
    ):
        service = build_service(db_session, slack)

        result = await process(service, message_event())

        assert result.outcome is SlackEventOutcome.QUEUED_START
        assert result.celery_task_id == "task-start"
        assert tasks["start"].calls == [("U_TEST_123", "Ev_TEST_1", "C_TEST_CHANNEL")]
        assert tasks["end"].calls == []

    async def test_the_end_command_queues_the_logout_task(
        self, db_session, employee, slack, tasks
    ):
        service = build_service(db_session, slack)

        result = await process(service, message_event(text="\\end"))

        assert result.outcome is SlackEventOutcome.QUEUED_END
        assert tasks["end"].calls == [("U_TEST_123", "Ev_TEST_1", "C_TEST_CHANNEL")]
        assert tasks["start"].calls == []

    async def test_commands_are_accepted_in_a_direct_message(
        self, db_session, employee, slack, tasks
    ):
        service = build_service(db_session, slack)

        result = await process(
            service, message_event(text="\\end", channel="D_TEST_DM", channel_type="im")
        )

        assert result.outcome is SlackEventOutcome.QUEUED_END

    async def test_direct_messages_can_be_disabled(
        self, db_session, employee, slack, tasks, monkeypatch
    ):
        monkeypatch.setattr(settings, "SLACK_ALLOW_DIRECT_MESSAGES", False)
        service = build_service(db_session, slack)

        result = await process(service, message_event(channel="D_TEST_DM", channel_type="im"))

        assert result.outcome is SlackEventOutcome.IGNORED_WRONG_CHANNEL
        assert tasks["start"].calls == []


class TestIgnoredEvents:
    async def test_bot_messages_never_trigger_automation(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)

        result = await process(service, message_event(bot_id="B_TEST"))

        assert result.outcome is SlackEventOutcome.IGNORED_BOT_EVENT
        assert tasks["start"].calls == []

    async def test_our_own_replies_never_trigger_automation(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)

        result = await process(service, message_event(subtype="bot_message"))

        assert result.outcome is SlackEventOutcome.IGNORED_BOT_EVENT

    @pytest.mark.parametrize("subtype", ["message_changed", "message_deleted", "channel_join"])
    async def test_edits_deletions_and_membership_churn_are_ignored(
        self, db_session, employee, slack, tasks, subtype
    ):
        service = build_service(db_session, slack)

        result = await process(service, message_event(subtype=subtype))

        assert result.outcome is SlackEventOutcome.IGNORED_MESSAGE_SUBTYPE
        assert tasks["start"].calls == []

    async def test_thread_replies_are_ignored(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)

        result = await process(service, message_event(thread_ts="1720000000.000001"))

        assert result.outcome is SlackEventOutcome.IGNORED_MESSAGE_SUBTYPE

    async def test_messages_from_other_channels_are_ignored(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)

        result = await process(service, message_event(channel="C_SOME_OTHER_CHANNEL"))

        assert result.outcome is SlackEventOutcome.IGNORED_WRONG_CHANNEL
        assert tasks["start"].calls == []

    async def test_unsupported_event_types_are_ignored(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)
        payload = message_event()
        payload["event"]["type"] = "reaction_added"

        result = await process(service, payload)

        assert result.outcome is SlackEventOutcome.IGNORED_UNSUPPORTED_EVENT

    async def test_ordinary_chatter_is_ignored(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)

        result = await process(service, message_event(text="morning everyone"))

        assert result.outcome is SlackEventOutcome.IGNORED_INVALID_FORMAT
        assert tasks["start"].calls == []

    async def test_a_payload_with_no_event_object_is_ignored(self, db_session, slack, tasks):
        service = build_service(db_session, slack)

        result = await process(service, {"type": "event_callback", "event_id": "Ev_1"})

        assert result.outcome is SlackEventOutcome.IGNORED_UNSUPPORTED_EVENT


class TestIdempotencyAndRegistration:
    async def test_a_duplicate_event_id_is_suppressed_before_queueing(
        self, db_session, employee, slack, tasks
    ):
        service = build_service(db_session, slack, duplicate=True)

        result = await process(service, message_event())

        assert result.outcome is SlackEventOutcome.DUPLICATE_EVENT
        assert tasks["start"].calls == []

    async def test_an_actionable_event_without_an_event_id_is_refused(
        self, db_session, employee, slack, tasks
    ):
        service = build_service(db_session, slack)
        payload = message_event()
        del payload["event_id"]

        result = await process(service, payload)

        assert result.outcome is SlackEventOutcome.IGNORED_MISSING_EVENT_ID
        assert tasks["start"].calls == []

    async def test_an_unregistered_user_is_told_so_and_nothing_is_queued(
        self, db_session, slack, tasks
    ):
        service = build_service(db_session, slack)

        result = await process(service, message_event(user="U_STRANGER"))

        assert result.outcome is SlackEventOutcome.EMPLOYEE_NOT_REGISTERED
        assert slack.kinds == ["unregistered"]
        assert tasks["start"].calls == []

    async def test_an_event_with_no_user_is_refused(self, db_session, employee, slack, tasks):
        service = build_service(db_session, slack)
        payload = message_event()
        del payload["event"]["user"]

        result = await process(service, payload)

        assert result.outcome is SlackEventOutcome.IGNORED_MISSING_USER


class TestBrokerFailure:
    async def test_a_broker_failure_surfaces_as_a_queue_error(
        self, db_session, employee, slack, monkeypatch
    ):
        monkeypatch.setattr(ses, "process_attendance_task", FakeTask(raises=True))
        service = build_service(db_session, slack)

        with pytest.raises(SlackEventQueueError):
            await process(service, message_event(text=VALID_START_REPORT))
