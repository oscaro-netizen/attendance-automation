from app.marsos.provider import AttendanceProvider, MarsOSAPIProvider, MarsOSPlaywrightProvider
from app.core.config import settings

def get_attendance_provider() -> AttendanceProvider:
    """
    Factory to return the appropriate attendance provider.
    Currently defaults to Playwright as requested, but can be swapped for API.
    """
    if settings.MARSOS_API_KEY:
        return MarsOSAPIProvider()
    return MarsOSPlaywrightProvider()
