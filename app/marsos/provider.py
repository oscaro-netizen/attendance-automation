from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
import asyncio
from playwright.async_api import async_playwright
from loguru import logger
from app.core.config import settings

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
    Playwright implementation for MarsOS attendance automation.
    """
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def login(self, email: str, password: str) -> bool:
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            
            await self.page.goto(f"{settings.MARSOS_BASE_URL}/login")
            await self.page.fill('input[name="email"]', email)
            await self.page.fill('input[name="password"]', password)
            await self.page.click('button[type="submit"]')
            
            # Wait for navigation or a specific element that indicates successful login
            await self.page.wait_for_selector('.dashboard-ready', timeout=30000)
            logger.info(f"Successfully logged in to MarsOS for {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to login to MarsOS: {str(e)}")
            if self.page:
                await self.page.screenshot(path=f"failure_login_{datetime.now().isoformat()}.png")
            await self.logout()
            return False

    async def start_attendance(self, employee_id: str) -> bool:
        try:
            if not self.page:
                raise Exception("Not logged in")
                
            await self.page.goto(f"{settings.MARSOS_BASE_URL}/attendance")
            
            # Check if already started
            already_started = await self.page.query_selector('.attendance-started-badge')
            if already_started:
                logger.info(f"Attendance already started for employee {employee_id}")
                return True # Treat as success or handle duplicate logic upstream
                
            await self.page.click('button#start-attendance')
            await self.page.wait_for_selector('.attendance-started-badge', timeout=10000)
            
            logger.info(f"Attendance started successfully for employee {employee_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start attendance in MarsOS: {str(e)}")
            if self.page:
                await self.page.screenshot(path=f"failure_attendance_{datetime.now().isoformat()}.png")
            return False

    async def logout(self) -> None:
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
        logger.info("Closed MarsOS browser session")
