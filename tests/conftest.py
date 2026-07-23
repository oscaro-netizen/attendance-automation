"""
Shared fixtures.

Settings come from environment defaults set before `app.*` is imported, so the
suite never depends on a developer's local .env, and never touches the network.
"""
import os

import pytest

TEST_SIGNING_SECRET = "test_signing_secret"

os.environ.setdefault("SLACK_SIGNING_SECRET", TEST_SIGNING_SECRET)
os.environ.setdefault("SLACK_CHANNEL_ID", "C_TEST")
os.environ.setdefault("TIMETRACK_BASE_URL", "https://timetrack.test")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Points the store at a throwaway SQLite file for the duration of a test."""
    from app.config import settings
    from app.store import init_db

    path = str(tmp_path / "employees.db")
    monkeypatch.setattr(settings, "DATABASE_PATH", path)
    init_db(path)
    return path
