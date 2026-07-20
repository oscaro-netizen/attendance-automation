"""Test doubles and payload builders shared across the suite."""
from typing import Any, Dict, List, Optional

from app.marsos.provider import AttendanceProvider

VALID_START_REPORT = (
    "July 13, 2026 - Start\n"
    "\n"
    "Tasks:\n"
    "• Task A\n"
    "\n"
    "Expected Today:\n"
    "• Goal A"
)


class FakeProvider(AttendanceProvider):
    """
    Records the calls made against it so tests can assert on the interaction,
    notably that `close()` is called exactly once.
    """

    def __init__(
        self,
        login_result: bool = True,
        start_result: bool = True,
        end_result: bool = True,
        raise_on: Optional[str] = None,
    ):
        self.login_result = login_result
        self.start_result = start_result
        self.end_result = end_result
        self.raise_on = raise_on
        self.calls: List[str] = []

    def _maybe_raise(self, name: str) -> None:
        if self.raise_on == name:
            raise RuntimeError(f"boom in {name}")

    async def login(self, email: str, password: str) -> bool:
        self.calls.append("login")
        self._maybe_raise("login")
        return self.login_result

    async def start_attendance(self, employee_id: str) -> bool:
        self.calls.append("start_attendance")
        self._maybe_raise("start_attendance")
        return self.start_result

    async def end_attendance(self, employee_id: str) -> bool:
        self.calls.append("end_attendance")
        self._maybe_raise("end_attendance")
        return self.end_result

    async def close(self) -> None:
        self.calls.append("close")
        self._maybe_raise("close")

    @property
    def close_count(self) -> int:
        return self.calls.count("close")


class FakeSlackClient:
    """Captures the replies the service would have posted to Slack."""

    def __init__(self) -> None:
        self.sent: List[Dict[str, Any]] = []

    def _record(self, kind: str, channel: str, user_id: str, **extra):
        self.sent.append({"kind": kind, "channel": channel, "user_id": user_id, **extra})
        return {"ok": True}

    async def send_message(self, channel: str, text: str, thread_ts: Optional[str] = None):
        self.sent.append({"kind": "message", "channel": channel, "text": text})
        return {"ok": True}

    async def send_success_reply(self, channel, user_id, start_time, thread_ts=None):
        return self._record("success", channel, user_id, start_time=start_time)

    async def send_duplicate_reply(self, channel, user_id, thread_ts=None):
        return self._record("duplicate", channel, user_id)

    async def send_failure_reply(self, channel, user_id, thread_ts=None):
        return self._record("failure", channel, user_id)

    async def send_end_success_reply(self, channel, user_id, end_time, thread_ts=None):
        return self._record("end_success", channel, user_id, end_time=end_time)

    async def send_end_failure_reply(self, channel, user_id, thread_ts=None):
        return self._record("end_failure", channel, user_id)

    async def send_unregistered_reply(self, channel, user_id, thread_ts=None):
        return self._record("unregistered", channel, user_id)

    async def send_credentials_error_reply(self, channel, user_id, thread_ts=None):
        return self._record("credentials_error", channel, user_id)

    @property
    def kinds(self) -> List[str]:
        return [item["kind"] for item in self.sent]


class FakeDeduplicator:
    """In-memory stand-in for the Redis-backed deduplicator."""

    def __init__(self, duplicate: bool = False):
        self.duplicate = duplicate
        self.seen: List[str] = []

    async def is_duplicate(self, event_id: Optional[str]) -> bool:
        if not event_id:
            return False
        self.seen.append(event_id)
        return self.duplicate


class FakeTask:
    """Stands in for a Celery task; records `.delay()` invocations."""

    def __init__(self, task_id: str = "task-123", raises: bool = False):
        self.task_id = task_id
        self.raises = raises
        self.calls: List[tuple] = []

    def delay(self, *args):
        if self.raises:
            raise RuntimeError("broker unreachable")
        self.calls.append(args)
        return type("AsyncResult", (), {"id": self.task_id})()


def message_event(
    text: str = VALID_START_REPORT,
    channel: str = "C_TEST_CHANNEL",
    user: str = "U_TEST_123",
    event_id: str = "Ev_TEST_1",
    **event_overrides,
) -> Dict[str, Any]:
    """Builds a Slack `event_callback` envelope for a channel message."""
    event: Dict[str, Any] = {
        "type": "message",
        "user": user,
        "channel": channel,
        "text": text,
        "ts": "1720000000.000100",
    }
    event.update(event_overrides)
    return {
        "type": "event_callback",
        "team_id": "T_TEST",
        "api_app_id": "A_TEST",
        "event": event,
        "event_id": event_id,
        "event_time": 1720000000,
    }
