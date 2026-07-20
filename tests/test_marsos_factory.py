"""Provider selection must never silently substitute a no-op implementation."""
import pytest

from app.core.config import settings
from app.marsos.factory import get_attendance_provider
from app.marsos.provider import MarsOSPlaywrightProvider


def test_defaults_to_the_playwright_provider(monkeypatch):
    monkeypatch.setattr(settings, "MARSOS_PROVIDER", "playwright")
    assert isinstance(get_attendance_provider(), MarsOSPlaywrightProvider)


def test_an_api_key_alone_does_not_switch_providers(monkeypatch):
    """
    Regression: the factory selected the (stubbed) API provider whenever
    MARSOS_API_KEY was set, so merely configuring a key turned every workday
    start into a no-op that still reported success to the employee.
    """
    monkeypatch.setattr(settings, "MARSOS_PROVIDER", "playwright")
    monkeypatch.setattr(settings, "MARSOS_API_KEY", "some-key")

    assert isinstance(get_attendance_provider(), MarsOSPlaywrightProvider)


def test_explicitly_selecting_the_api_provider_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "MARSOS_PROVIDER", "api")

    with pytest.raises(NotImplementedError):
        get_attendance_provider()


@pytest.mark.asyncio
async def test_closing_a_provider_that_never_logged_in_is_safe():
    """`close()` runs in a `finally` block, including after a failed login."""
    provider = MarsOSPlaywrightProvider()
    await provider.close()
    await provider.close()  # idempotent
