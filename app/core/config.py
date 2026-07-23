from typing import Literal, Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()  # Load environment variables from .env file


class Settings(BaseSettings):
    PROJECT_NAME: str = "Attendance Automation"
    API_V1_STR: str = "/api/v1"

    # Slack Configuration
    SLACK_SIGNING_SECRET: str
    SLACK_BOT_TOKEN: str
    SLACK_CHANNEL_ID: Optional[str] = None
    SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS: int = 300
    SLACK_EVENT_DEDUPE_TTL_SECONDS: int = 600
    # Whether employees may drive automation from a DM with the bot in addition
    # to the configured reporting channel.
    SLACK_ALLOW_DIRECT_MESSAGES: bool = True

    # Database Configuration
    DATABASE_URL: str
    DATABASE_ECHO: bool = False

    # Redis Configuration
    REDIS_URL: str

    # MarsOS Configuration
    MARSOS_BASE_URL: str

    # Encryption Key
    ENCRYPTION_KEY: str

    # OpenAPI / Swagger Documentation toggle
    # Set to False in production environment to hide /docs and /redoc
    ENABLE_DOCS: bool = True

    # Playwright Configuration
    PLAYWRIGHT_HEADLESS: bool = True
    # Directory holding persisted browser storage state. Point this at shared
    # storage when running more than one worker replica, or disable reuse.
    PLAYWRIGHT_SESSION_DIR: str = "sessions"
    PLAYWRIGHT_SESSION_REUSE: bool = True
    PLAYWRIGHT_ARTIFACT_DIR: str = "artifacts"

    # IANA timezone defining the company's calendar day, used for the
    # "already started today" rule and for clock times shown in Slack.
    ATTENDANCE_TIMEZONE: str = "UTC"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()
