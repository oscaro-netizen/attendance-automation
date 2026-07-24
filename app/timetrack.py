"""
Client for the TimeTrack API (https://time.marsos.io).

TimeTrack authenticates with a JWT sent as `Authorization: Bearer <token>`.
Each employee supplies their own token, so every call here acts as that person.

Endpoints used:

    GET  /api/attendance/today      current day's state
    POST /api/attendance/clock-in   start the workday
    POST /api/attendance/clock-out  end the workday
"""
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class TimeTrackError(Exception):
    """A TimeTrack call did not succeed."""


class TimeTrackAuthError(TimeTrackError):
    """The token was rejected -- almost always because it has expired."""


# Key spellings that may appear in the `today` payload. The exact shape has not
# been observed yet, so several plausible ones are accepted and an unrecognised
# payload is reported as "unknown" rather than guessed at.
_CLOCK_IN_KEYS = ("clockIn", "clock_in", "clockInTime", "clock_in_time", "checkIn", "check_in")
_CLOCK_OUT_KEYS = ("clockOut", "clock_out", "clockOutTime", "clock_out_time", "checkOut", "check_out")


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> tuple[bool, Any]:
    for key in keys:
        if key in payload:
            return True, payload[key]
    return False, None


def is_clocked_in(today: dict[str, Any]) -> bool | None:
    """
    Works out whether the employee is currently clocked in.

    Returns None when the payload cannot be interpreted, which callers treat as
    "proceed anyway" -- refusing to act because we could not read a status would
    be worse than a redundant call that TimeTrack can reject itself.
    """
    if not isinstance(today, dict):
        return None

    # Some APIs nest the day under wrapper keys like data -> current.
    for wrapper in ("data", "attendance", "today", "current"):
        inner = today.get(wrapper)
        if isinstance(inner, dict):
            today = inner

    has_in, clock_in = _first_present(today, _CLOCK_IN_KEYS)
    has_out, clock_out = _first_present(today, _CLOCK_OUT_KEYS)

    if not has_in and not has_out:
        logger.info("Could not interpret TimeTrack 'today' payload; keys=%s", sorted(today))
        return None

    # Clocked in means a start time exists and no end time has been recorded yet.
    return bool(clock_in) and not bool(clock_out)


class TimeTrackClient:
    def __init__(self, token: str, base_url: str | None = None, timeout: float | None = None):
        self._token = token
        self._base_url = (base_url or settings.TIMETRACK_BASE_URL).rstrip("/")
        self._timeout = timeout if timeout is not None else settings.TIMETRACK_TIMEOUT_SECONDS
        self._transport: httpx.AsyncBaseTransport | None = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                # TimeTrack sits behind Cloudflare, which is less suspicious of a
                # request that looks like it came from the app it serves.
                "Origin": self._base_url,
                "Referer": f"{self._base_url}/",
            },
        )

    async def _request(self, method: str, path: str) -> Any:
        async with self._client() as client:
            try:
                response = await client.request(method, path)
            except httpx.HTTPError as exc:
                raise TimeTrackError(f"{method} {path} failed: {exc}") from exc

        if response.status_code in (401, 403):
            raise TimeTrackAuthError(f"{method} {path} returned {response.status_code}; the token is invalid or expired")

        if response.status_code >= 400:
            raise TimeTrackError(f"{method} {path} returned {response.status_code}: {response.text[:200]}")

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    async def today(self) -> Any:
        return await self._request("GET", "/api/attendance/today")

    async def clock_in(self) -> Any:
        return await self._request("POST", "/api/attendance/clock-in")

    async def clock_out(self) -> Any:
        return await self._request("POST", "/api/attendance/clock-out")
