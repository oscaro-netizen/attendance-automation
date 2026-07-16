from slack_sdk.web.async_client import AsyncWebClient
from app.core.config import settings
from loguru import logger

class SlackClient:
    def __init__(self, client: AsyncWebClient = None):
        self.client = client or AsyncWebClient(token=settings.SLACK_BOT_TOKEN)

    async def send_message(self, channel: str, text: str, thread_ts: str = None):
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

    async def send_success_reply(self, channel: str, user_id: str, start_time: str, thread_ts: str = None):
        text = f"<@{user_id}> Attendance started successfully.\n\n*Start Time:*\n{start_time}"
        return await self.send_message(channel, text, thread_ts)

    async def send_duplicate_reply(self, channel: str, user_id: str, thread_ts: str = None):
        text = f"<@{user_id}> Attendance already started today."
        return await self.send_message(channel, text, thread_ts)

    async def send_failure_reply(self, channel: str, user_id: str, thread_ts: str = None):
        text = f"<@{user_id}> Unable to start attendance. The issue has been logged."
        return await self.send_message(channel, text, thread_ts)

    async def send_unregistered_reply(self, channel: str, user_id: str, thread_ts: str = None):
        text = (
            f"<@{user_id}> You are not registered for attendance automation yet. "
            f"Please contact an administrator to be added."
        )
        return await self.send_message(channel, text, thread_ts)
