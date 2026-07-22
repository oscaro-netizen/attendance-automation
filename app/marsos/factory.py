from app.core.config import settings
from app.marsos.provider import AttendanceProvider, MarsOSAPIProvider, MarsOSPlaywrightProvider


def get_attendance_provider() -> AttendanceProvider:
    """
    Returns the configured attendance provider.

    Selection is driven by the explicit `MARSOS_PROVIDER` setting. It is
    deliberately *not* inferred from `MARSOS_API_KEY` being present: the API
    provider is still a stub, and inferring it meant merely setting a key would
    silently disable all real automation while still reporting success.
    """
    if settings.MARSOS_PROVIDER == "api":
        return MarsOSAPIProvider()
    return MarsOSPlaywrightProvider()
