import pytest
from unittest.mock import AsyncMock, patch
from app.slack.client import SlackClient

@pytest.mark.asyncio
async def test_send_message_success():
    mock_async_web_client = AsyncMock()
    mock_async_web_client.chat_postMessage.return_value = {"ok": True, "ts": "12345"}
    
    slack_client = SlackClient(client=mock_async_web_client)
    
    response = await slack_client.send_message("C123", "Hello, world!")
    
    mock_async_web_client.chat_postMessage.assert_called_once_with(
        channel="C123",
        text="Hello, world!",
        thread_ts=None
    )
    assert response == {"ok": True, "ts": "12345"}

@pytest.mark.asyncio
async def test_send_message_failure():
    mock_async_web_client = AsyncMock()
    mock_async_web_client.chat_postMessage.side_effect = Exception("Slack API error")
    
    slack_client = SlackClient(client=mock_async_web_client)
    
    response = await slack_client.send_message("C123", "Hello, world!")
    
    mock_async_web_client.chat_postMessage.assert_called_once()
    assert response is None

@pytest.mark.asyncio
async def test_send_success_reply():
    with patch("app.slack.client.SlackClient.send_message", new_callable=AsyncMock) as mock_send_message:
        mock_send_message.return_value = {"ok": True}
        slack_client = SlackClient()
        response = await slack_client.send_success_reply("C123", "U123", "09:00 AM")
        
        expected_text = "<@U123> Attendance started successfully.\n\n*Start Time:*\n09:00 AM"
        mock_send_message.assert_called_once_with("C123", expected_text, None)
        assert response == {"ok": True}

@pytest.mark.asyncio
async def test_send_duplicate_reply():
    with patch("app.slack.client.SlackClient.send_message", new_callable=AsyncMock) as mock_send_message:
        mock_send_message.return_value = {"ok": True}
        slack_client = SlackClient()
        response = await slack_client.send_duplicate_reply("C123", "U123")
        
        expected_text = "<@U123> Attendance already started today."
        mock_send_message.assert_called_once_with("C123", expected_text, None)
        assert response == {"ok": True}

@pytest.mark.asyncio
async def test_send_failure_reply():
    with patch("app.slack.client.SlackClient.send_message", new_callable=AsyncMock) as mock_send_message:
        mock_send_message.return_value = {"ok": True}
        slack_client = SlackClient()
        response = await slack_client.send_failure_reply("C123", "U123")
        
        expected_text = "<@U123> Unable to start attendance. The issue has been logged."
        mock_send_message.assert_called_once_with("C123", expected_text, None)
        assert response == {"ok": True}
