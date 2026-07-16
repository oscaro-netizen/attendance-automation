from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

class Settings(BaseSettings):
    PROJECT_NAME: str = "Attendance Automation"
    API_V1_STR: str = "/api/v1"

    # Slack Configuration
    SLACK_SIGNING_SECRET: str
    SLACK_BOT_TOKEN: str
    SLACK_CHANNEL_ID: Optional[str] = None

    # Slack Events API pipeline configuration
    # Maximum allowed clock skew, in seconds, between the X-Slack-Request-Timestamp
    # header and server time before a request is rejected as a possible replay attack.
    # Slack's own recommendation is 5 minutes (300 seconds).
    SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS: int = 300

    # How long a Slack event_id is remembered for duplicate suppression.
    # Slack retries undelivered events up to 3 times over a window of several
    # minutes (immediately, then again after ~1 minute, then again after ~5
    # minutes), so this TTL must comfortably exceed that window.
    SLACK_EVENT_DEDUPE_TTL_SECONDS: int = 600

    # Database Configuration
    DATABASE_URL: str

    # Redis Configuration
    REDIS_URL: str

    # MarsOS Configuration
    MARSOS_BASE_URL: str
    MARSOS_API_KEY: Optional[str] = None

    # Encryption Key
    ENCRYPTION_KEY: str

    # Playwright Configuration
    PLAYWRIGHT_HEADLESS: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
