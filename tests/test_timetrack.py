"""The TimeTrack client: auth header, error mapping, and reading the day's state."""
import httpx
import pytest

from app.timetrack import TimeTrackAuthError, TimeTrackClient, TimeTrackError, is_clocked_in


def client_with(handler) -> TimeTrackClient:
    client = TimeTrackClient(token="test-token", base_url="https://timetrack.test")
    client._transport = httpx.MockTransport(handler)
    return client


async def test_the_token_is_sent_as_a_bearer_header():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["url"] = str(request.url)
        seen["method"] = request.method
        return httpx.Response(200, json={"ok": True})

    await client_with(handler).clock_in()
    assert seen["auth"] == "Bearer test-token"
    assert seen["url"] == "https://timetrack.test/api/attendance/clock-in"
    assert seen["method"] == "POST"


async def test_clock_out_hits_its_own_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={})

    await client_with(handler).clock_out()
    assert seen["url"] == "https://timetrack.test/api/attendance/clock-out"


@pytest.mark.parametrize("status_code", [401, 403])
async def test_a_rejected_token_raises_an_auth_error(status_code):
    """Auth failures are distinguished so the operator knows to re-register a token."""
    handler = lambda request: httpx.Response(status_code, json={"error": "nope"})  # noqa: E731
    with pytest.raises(TimeTrackAuthError):
        await client_with(handler).today()


async def test_a_server_error_raises_a_generic_error():
    handler = lambda request: httpx.Response(500, text="boom")  # noqa: E731
    with pytest.raises(TimeTrackError) as exc:
        await client_with(handler).clock_in()
    assert not isinstance(exc.value, TimeTrackAuthError)


async def test_a_network_failure_raises_rather_than_hanging():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(TimeTrackError):
        await client_with(handler).today()


async def test_an_empty_body_is_not_a_failure():
    handler = lambda request: httpx.Response(204)  # noqa: E731
    assert await client_with(handler).clock_in() is None


# --- reading the day's state ---------------------------------------------------


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"clockIn": "09:00", "clockOut": None}, True),
        ({"clockIn": "09:00", "clockOut": "17:00"}, False),
        ({"clock_in": "09:00", "clock_out": None}, True),
        ({"clock_in": None, "clock_out": None}, False),
        ({"data": {"clockIn": "09:00", "clockOut": None}}, True),
        ({"checkIn": "09:00", "checkOut": "17:00"}, False),
    ],
)
def test_the_day_state_is_read_from_known_payload_shapes(payload, expected):
    assert is_clocked_in(payload) is expected


@pytest.mark.parametrize("payload", [{}, {"something": "else"}, None, "not a dict", []])
def test_an_unreadable_payload_reports_unknown(payload):
    """
    Unknown means "proceed anyway". Refusing to act because we could not parse a
    status would be worse than a redundant call TimeTrack can reject itself.
    """
    assert is_clocked_in(payload) is None
