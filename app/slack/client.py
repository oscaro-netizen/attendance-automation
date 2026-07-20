from typing import Optional

from loguru import logger
from slack_sdk.web.async_client import AsyncWebClient

from app.core.config import settings


class SlackClient:
    """Thin wrapper over `chat.postMessage` with the canned replies this app sends."""

    def __init__(self, client: Optional[AsyncWebClient] = None):
        self.client = client or AsyncWebClient(token=settings.SLACK_BOT_TOKEN)

    async def send_message(self, channel: str, text: str, thread_ts: Optional[str] = None):
        try:
            response = await self.client.chat_postMessage(
                channel=channel,
                text=text,
                thread_ts=thread_ts
            )
            return response
        except Exception as e:
            logger.error(f"Failed to send Slack message: {str(e)}")
            return None

    # --- Start-of-day replies -------------------------------------------------

    async def send_success_reply(self, channel: str, user_id: str, start_time: str, thread_ts: Optional[str] = None):
        text = f"<@{user_id}> Attendance started successfully.\n\n*Start Time:*\n{start_time}"
        return await self.send_message(channel, text, thread_ts)

    async def send_duplicate_reply(self, channel: str, user_id: str, thread_ts: Optional[str] = None):
        text = f"<@{user_id}> Attendance already started today."
        return await self.send_message(channel, text, thread_ts)

    async def send_failure_reply(self, channel: str, user_id: str, thread_ts: Optional[str] = None):
        text = f"<@{user_id}> Unable to start attendance. The issue has been logged."
        return await self.send_message(channel, text, thread_ts)

    # --- End-of-day replies ---------------------------------------------------

    async def send_end_success_reply(self, channel: str, user_id: str, end_time: str, thread_ts: Optional[str] = None):
        text = f"✅ Workday ended successfully for <@{user_id}>! See you next time. 👋\n\n*End Time:*\n{end_time}"
        return await self.send_message(channel, text, thread_ts)

    async def send_end_failure_reply(self, channel: str, user_id: str, thread_ts: Optional[str] = None):
        text = (
            f"<@{user_id}> ⚠️ I couldn't end your workday in MarsOS. "
            "Are you sure you started your shift? The issue has been logged."
        )
        return await self.send_message(channel, text, thread_ts)

    # --- Shared error replies -------------------------------------------------

    async def send_unregistered_reply(self, channel: str, user_id: str, thread_ts: Optional[str] = None):
        text = f"<@{user_id}> ⚠️ You are not registered in the system. Please contact an admin."
        return await self.send_message(channel, text, thread_ts)

    async def send_credentials_error_reply(self, channel: str, user_id: str, thread_ts: Optional[str] = None):
        text = (
            f"<@{user_id}> ❌ Your MarsOS credentials are missing or unreadable. "
            "Please contact an admin to re-register them."
        )
        return await self.send_message(channel, text, thread_ts)
