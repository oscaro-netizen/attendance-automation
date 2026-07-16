import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.slack_schemas import SlackEventEnvelope
from app.services.slack_event_service import (
    SlackEventOutcome,
    SlackEventQueueError,
    SlackEventService,
)


VALID_TEXT = "July 15, 2026 - Start\n\nTasks:\n\u2022 Task A\n\nExpected Today:\n\u2022 Goal A"


def _envelope(**event_overrides) -> SlackEventEnvelope:
    event = {
        "type": "message",
        "channel": "C123",
        "user": "U100",
        "text": VALID_TEXT,
        "ts": "1626282600.000100",
    }
    event.update(event_overrides)
    return SlackEventEnvelope.model_validate(
        {
            "token": "verification-token",
            "team_id": "T123",
            "api_app_id": "A123",
            "type": "event_callback",
            "event_id": "Ev001",
            "event_time": 1626282600,
            "event": event,
        }
    )


def _stop_envelope(**event_overrides):
    """A DM-shaped stop message, unless overridden."""
    defaults = {
        "channel": "D999",
        "channel_type": "im",
        "text": "July 16, 2026 - End",
    }
    defaults.update(event_overrides)
    return _envelope(**defaults)


def _service(employee=None, is_duplicate=False):
    db = MagicMock()
    deduplicator = AsyncMock()
    deduplicator.is_duplicate.return_value = is_duplicate

    employee_repo = AsyncMock()
    employee_repo.get_by_slack_id.return_value = employee

    slack_client = AsyncMock()

    service = SlackEventService(
        db=db,
        deduplicator=deduplicator,
        employee_repo=employee_repo,
        slack_client=slack_client,
    )
    return service, deduplicator, employee_repo, slack_client


class _FakeEmployee:
    id = 1
    slack_user_id = "U100"
    marsos_email = "alice@example.com"


@pytest.mark.asyncio
async def test_ignores_bot_id_event():
    service, *_ = _service()
    envelope = _envelope(bot_id="B123")
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_BOT_EVENT


@pytest.mark.asyncio
async def test_ignores_bot_message_subtype():
    service, *_ = _service()
    envelope = _envelope(subtype="bot_message")
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_BOT_EVENT


@pytest.mark.asyncio
async def test_ignores_unsupported_event_type():
    service, *_ = _service()
    envelope = _envelope(type="reaction_added")
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_UNSUPPORTED_EVENT


@pytest.mark.asyncio
async def test_ignores_message_edit_subtype():
    service, *_ = _service()
    envelope = _envelope(subtype="message_changed")
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_MESSAGE_SUBTYPE


@pytest.mark.asyncio
async def test_ignores_thread_reply():
    service, *_ = _service()
    envelope = _envelope(thread_ts="1626282500.000000")
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_MESSAGE_SUBTYPE


@pytest.mark.asyncio
async def test_ignores_wrong_channel():
    service, *_ = _service()
    envelope = _envelope(channel="C999")
    with patch("app.services.slack_event_service.settings") as mock_settings:
        mock_settings.SLACK_CHANNEL_ID = "C123"
        result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_WRONG_CHANNEL


@pytest.mark.asyncio
async def test_ignores_invalid_message_format():
    service, *_ = _service()
    envelope = _envelope(text="just chatting, not a report")
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_INVALID_FORMAT


@pytest.mark.asyncio
async def test_missing_event_id_is_not_queued():
    service, deduplicator, *_ = _service()
    envelope = _envelope()
    envelope = envelope.model_copy(update={"event_id": None})
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_MISSING_EVENT_ID
    deduplicator.is_duplicate.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_event_is_suppressed():
    service, deduplicator, employee_repo, _ = _service(is_duplicate=True)
    envelope = _envelope()
    result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.DUPLICATE_EVENT
    deduplicator.is_duplicate.assert_called_once_with("Ev001")
    employee_repo.get_by_slack_id.assert_not_called()


@pytest.mark.asyncio
async def test_unregistered_employee_notified_and_not_queued():
    service, deduplicator, employee_repo, slack_client = _service(employee=None, is_duplicate=False)
    envelope = _envelope()
    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.EMPLOYEE_NOT_REGISTERED
    slack_client.send_unregistered_reply.assert_called_once_with("C123", "U100")
    mock_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_successful_dispatch_queues_celery_task():
    service, deduplicator, employee_repo, slack_client = _service(
        employee=_FakeEmployee(), is_duplicate=False
    )
    envelope = _envelope()
    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="celery-task-123")
        result = await service.process_event(envelope, request_id="rid")

    assert result.outcome == SlackEventOutcome.QUEUED
    assert result.celery_task_id == "celery-task-123"
    mock_task.delay.assert_called_once_with("U100", "Ev001", "C123")


@pytest.mark.asyncio
async def test_stop_dm_dispatches_stop_task():
    service, deduplicator, employee_repo, slack_client = _service(
        employee=_FakeEmployee(), is_duplicate=False
    )
    envelope = _stop_envelope().model_copy(update={"event_id": "Ev-stop-1"})
    with patch("app.services.slack_event_service.process_attendance_stop_task") as mock_stop_task:
        mock_stop_task.delay.return_value = MagicMock(id="celery-stop-task-1")
        result = await service.process_event(envelope, request_id="rid")

    assert result.outcome == SlackEventOutcome.QUEUED_STOP
    assert result.celery_task_id == "celery-stop-task-1"
    mock_stop_task.delay.assert_called_once_with("U100", "Ev-stop-1", "D999")


@pytest.mark.asyncio
async def test_stop_message_in_team_channel_is_rejected():
    """A "- End" message posted in the public channel (not a DM) must not trigger automation."""
    service, deduplicator, employee_repo, slack_client = _service(employee=_FakeEmployee())
    envelope = _stop_envelope(channel="C123", channel_type="channel")
    with patch("app.services.slack_event_service.process_attendance_stop_task") as mock_stop_task:
        result = await service.process_event(envelope, request_id="rid")

    assert result.outcome == SlackEventOutcome.IGNORED_STOP_NOT_DM
    mock_stop_task.delay.assert_not_called()


@pytest.mark.asyncio
async def test_start_message_sent_as_dm_is_rejected_if_channel_restricted():
    """A Start report sent as a DM instead of the monitored channel is still subject to the channel rule."""
    service, *_ = _service()
    envelope = _envelope(channel="D999", channel_type="im")
    with patch("app.services.slack_event_service.settings") as mock_settings:
        mock_settings.SLACK_CHANNEL_ID = "C123"
        result = await service.process_event(envelope, request_id="rid")
    assert result.outcome == SlackEventOutcome.IGNORED_WRONG_CHANNEL


@pytest.mark.asyncio
async def test_celery_dispatch_failure_raises_queue_error():
    service, deduplicator, employee_repo, slack_client = _service(
        employee=_FakeEmployee(), is_duplicate=False
    )
    envelope = _envelope()
    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        mock_task.delay.side_effect = ConnectionError("broker unreachable")
        with pytest.raises(SlackEventQueueError):
            await service.process_event(envelope, request_id="rid")
