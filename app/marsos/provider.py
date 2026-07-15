from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
import asyncio
import json
import os
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger
from app.core.config import settings

# Directory for storing browser sessions and traces
SESSION_DIR = "sessions"
TRACE_DIR = "traces"
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(TRACE_DIR, exist_ok=True)

class AttendanceProvider(ABC):
    @abstractmethod
    async def login(self, email: str, password: str) -> bool:
        pass

    @abstractmethod
    async def start_attendance(self, employee_id: str) -> bool:
        pass

    @abstractmethod
    async def logout(self) -> None:
        pass

class MarsOSAPIProvider(AttendanceProvider):
    """
    Placeholder for MarsOS API implementation if available.
    """
    async def login(self, email: str, password: str) -> bool:
        # Implement API login
        return True

    async def start_attendance(self, employee_id: str) -> bool:
        # Implement API start attendance
        return True

    async def logout(self) -> None:
        pass

class MarsOSPlaywrightProvider(AttendanceProvider):
    """
    Playwright implementation for MarsOS attendance automation with session persistence.
    """
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.trace_saved = False

    def _get_session_path(self, email: str) -> str:
        # Sanitize email for filename
        safe_email = "".join([c if c.isalnum() else "_" for c in email])
        return os.path.join(SESSION_DIR, f"session_{safe_email}.json")

    async def login(self, email: str, password: str) -> bool:
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
            
            session_path = self._get_session_path(email)
            
            # Try to load existing session
            if os.path.exists(session_path):
                logger.info(f"Attempting to reuse session for {email}")
                self.context = await self.browser.new_context(storage_state=session_path)
            else:
                self.context = await self.browser.new_context()

            # Start Playwright tracing
            await self.context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self.trace_saved = False

            self.page = await self.context.new_page()
            
            # Navigate to a page that requires login to check if session is valid
            await self.page.goto(f"{settings.MARSOS_BASE_URL}/dashboard")
            
            # Check if we are redirected to login
            if "/login" in self.page.url:
                logger.info(f"Session expired or missing for {email}. Logging in...")
                await self.page.goto(f"{settings.MARSOS_BASE_URL}/login")
                
                # Use more robust selectors (preferring accessible roles or IDs)
                await self.page.get_by_label("Email").fill(email)
                await self.page.get_by_label("Password").fill(password)
                await self.page.get_by_role("button", name="Sign In").click()
                
                # Wait for navigation or a specific element that indicates successful login
                # Dashboard indicator should be stable
                await self.page.wait_for_selector("[data-testid='dashboard-container']", timeout=30000)
                
                # Save the session for future use
                await self.context.storage_state(path=session_path)
                logger.info(f"Successfully logged in and saved session for {email}")
            else:
                logger.info(f"Successfully reused session for {email}")
                
            return True
        except Exception as e:
            logger.error(f"Failed to login to MarsOS: {str(e)}")
            if self.context and not self.trace_saved:
                trace_path = os.path.join(TRACE_DIR, f"failure_login_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                await self.context.tracing.stop(path=trace_path)
                self.trace_saved = True
                logger.info(f"Saved failure login trace to {trace_path}")
            if self.page:
                await self.page.screenshot(path=f"failure_login_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            await self.close()
            return False

    async def start_attendance(self, employee_id: str) -> bool:
        try:
            if not self.page:
                raise Exception("Not logged in")
                
            await self.page.goto(f"{settings.MARSOS_BASE_URL}/attendance")
            
            # Check if already started using a more robust data-testid or accessible name
            already_started = await self.page.query_selector("[data-testid='attendance-status-started']")
            if already_started:
                logger.info(f"Attendance already started for employee {employee_id}")
                return True
                
            # Use robust button selection
            start_button = self.page.get_by_role("button", name="Start Workday")
            await start_button.click()
            
            # Wait for success indicator
            await self.page.wait_for_selector("[data-testid='attendance-status-started']", timeout=15000)
            
            logger.info(f"Attendance started successfully for employee {employee_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start attendance in MarsOS: {str(e)}")
            if self.context and not self.trace_saved:
                trace_path = os.path.join(TRACE_DIR, f"failure_attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
                await self.context.tracing.stop(path=trace_path)
                self.trace_saved = True
                logger.info(f"Saved failure attendance trace to {trace_path}")
            if self.page:
                await self.page.screenshot(path=f"failure_attendance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            return False

    async def close(self) -> None:
        """Closes browser and stops playwright."""
        if self.context:
            try:
                if not getattr(self, "trace_saved", False):
                    await self.context.tracing.stop()
            except Exception as e:
                logger.error(f"Failed to stop Playwright tracing on close: {str(e)}")
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Closed MarsOS browser session")

    async def logout(self) -> None:
        """Alias for close to maintain interface consistency."""
        await self.close()
