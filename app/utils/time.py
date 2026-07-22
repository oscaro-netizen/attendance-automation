"""
Time helpers.

Every `DateTime` column in `app.models.models` is naive, and the convention is
that a naive value is **UTC**. Business rules such as "has this employee already
started today?" are, however, expressed in the *company's* local calendar day,
which is configured via `ATTENDANCE_TIMEZONE`.

Keeping those two concerns separate here avoids the previous bug where rows were
written with `datetime.now()` (server-local, naive) while the model default used
UTC, so the two disagreed by the server's UTC offset.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

from app.core.config import settings


def get_local_timezone() -> ZoneInfo:
    """Resolves `ATTENDANCE_TIMEZONE`, falling back to UTC if it is unknown."""
    try:
        return ZoneInfo(settings.ATTENDANCE_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            f"Unknown ATTENDANCE_TIMEZONE={settings.ATTENDANCE_TIMEZONE!r}; falling back to UTC"
        )
        return ZoneInfo("UTC")


def utc_now() -> datetime:
    """Current UTC time as a naive datetime, matching how columns are stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_now() -> datetime:
    """Current time as an aware datetime in the configured local timezone."""
    return datetime.now(get_local_timezone())


def local_today() -> date:
    """The current calendar day in the configured local timezone."""
    return local_now().date()


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """
    Returns the [start, end) bounds of a local calendar day expressed as naive
    UTC datetimes, suitable for comparing against stored column values.
    """
    tz = get_local_timezone()
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def to_local_display(moment: datetime) -> str:
    """Formats a naive-UTC datetime as a human-readable local clock time."""
    aware_utc = moment.replace(tzinfo=timezone.utc)
    return aware_utc.astimezone(get_local_timezone()).strftime("%I:%M %p %Z")
