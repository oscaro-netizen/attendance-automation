"""`run_action` -- the part that actually talks to TimeTrack."""
import httpx
import pytest

import app.main as main
from app.messages import Action
from app.timetrack import TimeTrackClient


def install_client(monkeypatch, handler):
    """Routes every TimeTrackClient the code creates through a mock transport."""
    calls = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return handler(request)

    original_init = TimeTrackClient.__init__

    def patched_init(self, token, base_url=None, timeout=None):
        original_init(self, token, base_url="https://timetrack.test", timeout=5)
        self._transport = httpx.MockTransport(record)

    monkeypatch.setattr(TimeTrackClient, "__init__", patched_init)
    return calls


def responder(today_payload, status_code=200):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/today"):
            return httpx.Response(200, json=today_payload)
        return httpx.Response(status_code, json={"ok": True})

    return handler


async def test_clock_in_is_sent_when_not_already_clocked_in(monkeypatch):
    calls = install_client(monkeypatch, responder({"clockIn": None, "clockOut": None}))
    await main.run_action("U1", Action.CLOCK_IN, "tok")
    assert ("POST", "/api/attendance/clock-in") in calls


async def test_clock_in_is_skipped_when_already_clocked_in(monkeypatch):
    """Slack redelivery must not open a second session."""
    calls = install_client(monkeypatch, responder({"clockIn": "09:00", "clockOut": None}))
    await main.run_action("U1", Action.CLOCK_IN, "tok")
    assert ("POST", "/api/attendance/clock-in") not in calls


async def test_clock_out_is_skipped_when_already_clocked_out(monkeypatch):
    calls = install_client(monkeypatch, responder({"clockIn": "09:00", "clockOut": "17:00"}))
    await main.run_action("U1", Action.CLOCK_OUT, "tok")
    assert ("POST", "/api/attendance/clock-out") not in calls


async def test_clock_out_is_sent_when_currently_clocked_in(monkeypatch):
    calls = install_client(monkeypatch, responder({"clockIn": "09:00", "clockOut": None}))
    await main.run_action("U1", Action.CLOCK_OUT, "tok")
    assert ("POST", "/api/attendance/clock-out") in calls


async def test_an_unreadable_today_payload_still_performs_the_action(monkeypatch):
    """If we cannot read the state, act anyway rather than silently doing nothing."""
    calls = install_client(monkeypatch, responder({"unexpected": "shape"}))
    await main.run_action("U1", Action.CLOCK_IN, "tok")
    assert ("POST", "/api/attendance/clock-in") in calls


async def test_an_expired_token_does_not_raise(monkeypatch, caplog):
    """This runs after the response was sent; an exception here has nowhere to go."""
    handler = lambda request: httpx.Response(401, json={"error": "expired"})  # noqa: E731
    install_client(monkeypatch, handler)
    await main.run_action("U1", Action.CLOCK_IN, "tok")  # must not raise
    assert "token" in caplog.text.lower()


async def test_a_timetrack_outage_does_not_raise(monkeypatch, caplog):
    handler = lambda request: httpx.Response(503, text="unavailable")  # noqa: E731
    install_client(monkeypatch, handler)
    await main.run_action("U1", Action.CLOCK_IN, "tok")  # must not raise
    assert "failed" in caplog.text.lower()
