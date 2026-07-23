"""Application settings, loaded from the environment (or a local .env file)."""
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    # --- Slack ---------------------------------------------------------------
    # Used to verify that inbound webhooks really came from Slack. This is the
    # only Slack credential the service needs; it never posts messages, so no
    # bot token and no chat:write scope are required.
    SLACK_SIGNING_SECRET: str

    # When set, only messages from this channel are acted on. When unset, any
    # conversation the Slack app is subscribed to is accepted.
    SLACK_CHANNEL_ID: Optional[str] = None

    # How old a signed Slack request may be before it is rejected as a replay.
    SLACK_TIMESTAMP_TOLERANCE_SECONDS: int = 300

    # --- TimeTrack -------------------------------------------------------------
    TIMETRACK_BASE_URL: str = "https://time.marsos.io"
    TIMETRACK_TIMEOUT_SECONDS: float = 15.0

    # --- Storage ----------------------------------------------------------------
    # SQLite file holding the Slack-user -> TimeTrack-token mapping. That mapping
    # is the only state this service keeps; attendance itself is recorded by
    # TimeTrack.
    DATABASE_PATH: str = "data/employees.db"

    # --- Misc ---------------------------------------------------------------------
    # The OpenAPI schema lists every route and request shape. Nothing in
    # production consumes it, so it is off unless explicitly enabled.
    ENABLE_API_DOCS: bool = False

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
