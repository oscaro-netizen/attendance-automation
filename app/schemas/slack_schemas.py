"""
Pydantic schemas for the Slack Events API payloads consumed by
`app.api.slack_events`.

These models intentionally use `extra="allow"` because Slack's event
payloads vary by event type and Slack may add new fields to the envelope
or to individual event objects without notice. Only the fields the
processing pipeline actually inspects are declared explicitly; everything
else passes through untouched rather than causing a validation failure.
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class SlackEventPayload(BaseModel):
    """
    The inner `event` object of a Slack `event_callback` payload.

    Reference: https://api.slack.com/events/message
    """

    model_config = ConfigDict(extra="allow")

    type: str
    user: Optional[str] = None
    bot_id: Optional[str] = None
    channel: Optional[str] = None
    channel_type: Optional[str] = None
    text: Optional[str] = None
    subtype: Optional[str] = None
    thread_ts: Optional[str] = None
    ts: Optional[str] = None

    @field_validator("type")
    @classmethod
    def type_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("event.type must not be blank")
        return value


class SlackEventEnvelope(BaseModel):
    """
    The top-level payload FastAPI receives on `POST /api/v1/slack/events`.

    Covers both the `url_verification` handshake and `event_callback`
    notifications. Reference: https://api.slack.com/apis/events-api
    """

    model_config = ConfigDict(extra="allow")

    type: str
    token: Optional[str] = None
    team_id: Optional[str] = None
    api_app_id: Optional[str] = None
    challenge: Optional[str] = None
    event: Optional[SlackEventPayload] = None
    event_id: Optional[str] = None
    event_time: Optional[int] = None

    @field_validator("type")
    @classmethod
    def type_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("payload.type must not be blank")
        return value

    @property
    def is_url_verification(self) -> bool:
        return self.type == "url_verification"

    @property
    def is_event_callback(self) -> bool:
        return self.type == "event_callback"
