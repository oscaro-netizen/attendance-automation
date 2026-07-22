import os
from abc import ABC, abstractmethod
from typing import Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.core.config import settings
from app.utils.time import utc_now


class AttendanceProvider(ABC):
    """
    A backend capable of driving a MarsOS workday on an employee's behalf.

    Lifecycle: `login()` -> `start_attendance()` / `end_attendance()` -> `close()`.
    `close()` must be safe to call more than once and safe to call after a failed
    login, because callers release the provider from a `finally` block.
    """

    @abstractmethod
    async def login(self, email: str, password: str) -> bool:
        ...

    @abstractmethod
    async def start_attendance(self, employee_id: str) -> bool:
        ...

    @abstractmethod
    async def end_attendance(self, employee_id: str) -> bool:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class MarsOSAPIProvider(AttendanceProvider):
    """
    Placeholder for a future MarsOS HTTP API implementation.

    Deliberately unusable: the previous stub returned `True` from every method,
    which meant selecting this provider silently reported success to employees
    while doing nothing in MarsOS.
    """

    _NOT_IMPLEMENTED = (
        "The MarsOS API provider is not implemented. "
        "Set MARSOS_PROVIDER=playwright until a real API integration exists."
    )

    def __init__(self) -> None:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    async def login(self, email: str, password: str) -> bool:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    async def start_attendance(self, employee_id: str) -> bool:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    async def end_attendance(self, employee_id: str) -> bool:
        raise NotImplementedError(self._NOT_IMPLEMENTED)

    async def close(self) -> None:
        raise NotImplementedError(self._NOT_IMPLEMENTED)


class MarsOSPlaywrightProvider(AttendanceProvider):
    """
    Playwright implementation for MarsOS attendance automation with optional
    session persistence (storage state reused across runs to skip the login form).
    """

    LOGIN_TIMEOUT_MS = 30_000
    ACTION_TIMEOUT_MS = 15_000
    BUTTON_TIMEOUT_MS = 10_000

    def __init__(self) -> None:
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._closed = False

    # --- Session / artifact paths ---------------------------------------------

    def _get_session_path(self, email: str) -> str:
        os.makedirs(settings.PLAYWRIGHT_SESSION_DIR, exist_ok=True)
        # Sanitize email for filename
        safe_email = "".join([c if c.isalnum() else "_" for c in email])
        return os.path.join(settings.PLAYWRIGHT_SESSION_DIR, f"session_{safe_email}.json")

    async def _capture_failure(self, label: str) -> None:
        """Best-effort screenshot; never raises into the caller's error path."""
        if not self.page:
            return
        try:
            os.makedirs(settings.PLAYWRIGHT_ARTIFACT_DIR, exist_ok=True)
            path = os.path.join(
                settings.PLAYWRIGHT_ARTIFACT_DIR,
                f"failure_{label}_{utc_now().strftime('%Y%m%d_%H%M%S')}.png",
            )
            await self.page.screenshot(path=path)
            logger.info(f"Saved failure screenshot to {path}")
        except Exception as exc:
            logger.warning(f"Could not capture failure screenshot: {exc}")

    # --- Lifecycle --------------------------------------------------------------

    async def login(self, email: str, password: str) -> bool:
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)

            session_path = self._get_session_path(email)
            reuse_session = settings.PLAYWRIGHT_SESSION_REUSE and os.path.exists(session_path)

            if reuse_session:
                logger.info(f"Attempting to reuse session for {email}")
                self.context = await self.browser.new_context(storage_state=session_path)
            else:
                self.context = await self.browser.new_context()

            self.page = await self.context.new_page()

            # Navigate to a page that requires login to check if the session is valid
            await self.page.goto(f"{settings.MARSOS_BASE_URL}/dashboard")

            # Check if we are redirected to login
            if "/login" in self.page.url:
                logger.info(f"Session expired or missing for {email}. Logging in...")
                await self.page.goto(f"{settings.MARSOS_BASE_URL}/login")

                # Prefer accessible roles/labels over brittle CSS selectors
                await self.page.get_by_label("Email").fill(email)
                await self.page.get_by_label("Password").fill(password)
                await self.page.get_by_role("button", name="Sign In").click()

                # Dashboard indicator should be stable
                await self.page.wait_for_selector(
                    "[data-testid='dashboard-container']", timeout=self.LOGIN_TIMEOUT_MS
                )

                if settings.PLAYWRIGHT_SESSION_REUSE:
                    await self.context.storage_state(path=session_path)
                logger.info(f"Successfully logged in for {email}")
            else:
                logger.info(f"Successfully reused session for {email}")

            return True
        except Exception as e:
            logger.error(f"Failed to login to MarsOS: {str(e)}")
            await self._capture_failure("login")
            await self.close()
            return False

    async def start_attendance(self, employee_id: str) -> bool:
        try:
            if not self.page:
                logger.error("No active page found. Ensure login() was called first.")
                return False

            await self.page.goto(f"{settings.MARSOS_BASE_URL}/attendance")

            # Already-started is a success, not a failure: MarsOS is in the desired state.
            already_started = await self.page.query_selector("[data-testid='attendance-status-started']")
            if already_started:
                logger.info(f"Attendance already started for employee {employee_id}")
                return True

            start_button = self.page.get_by_role("button", name="Start Workday")
            await start_button.wait_for(state="visible", timeout=self.BUTTON_TIMEOUT_MS)
            await start_button.click()

            await self.page.wait_for_selector(
                "[data-testid='attendance-status-started']", timeout=self.ACTION_TIMEOUT_MS
            )

            logger.info(f"Attendance started successfully for employee {employee_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start attendance in MarsOS: {str(e)}")
            await self._capture_failure("start")
            return False

    async def end_attendance(self, employee_id: str) -> bool:
        """Navigates to the attendance page and clicks the 'End Workday' button."""
        try:
            if not self.page:
                logger.error("No active page found. Ensure login() was called first.")
                return False

            await self.page.goto(f"{settings.MARSOS_BASE_URL}/attendance")

            # Already-stopped is a success for the same reason as above.
            already_stopped = await self.page.query_selector("[data-testid='attendance-status-stopped']")
            if already_stopped:
                logger.info(f"Attendance already stopped for employee {employee_id}")
                return True

            # Note: if the button text differs (e.g. 'Clock Out'), change it here.
            stop_button = self.page.get_by_role("button", name="End Workday")
            await stop_button.wait_for(state="visible", timeout=self.BUTTON_TIMEOUT_MS)
            await stop_button.click()

            await self.page.wait_for_selector(
                "[data-testid='attendance-status-stopped']", timeout=self.ACTION_TIMEOUT_MS
            )
            logger.info(f"Attendance stopped successfully for employee {employee_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop attendance in MarsOS: {str(e)}")
            await self._capture_failure("end")
            return False

    async def close(self) -> None:
        """
        Releases browser resources. Idempotent and exception-safe: callers invoke
        this from a `finally` block, where a raised error would mask the real one
        (and previously turned successful runs into Celery retries).
        """
        if self._closed:
            return
        self._closed = True

        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception as exc:
                logger.warning(f"Error while closing MarsOS browser: {exc}")

        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception as exc:
                logger.warning(f"Error while stopping Playwright: {exc}")

        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        logger.info("Closed MarsOS browser session")
