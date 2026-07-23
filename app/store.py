"""
The Slack-user -> TimeTrack-token mapping.

This is the only state the service keeps. Attendance records live in TimeTrack,
which is their system of record, so there is nothing else worth storing.

SQLite is used directly: one table, three columns, no ORM and no migrations.
"""
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from app.config import settings

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    slack_user_id    TEXT PRIMARY KEY,
    timetrack_token  TEXT NOT NULL,
    label            TEXT
)
"""


@contextmanager
def _connect(path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    db_path = path or settings.DATABASE_PATH
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    connection = sqlite3.connect(db_path)
    try:
        connection.row_factory = sqlite3.Row
        yield connection
        connection.commit()
    finally:
        connection.close()

    # The file holds bearer tokens, so keep it readable only by its owner.
    if os.path.exists(db_path):
        os.chmod(db_path, 0o600)


def init_db(path: Optional[str] = None) -> None:
    with _connect(path) as connection:
        connection.execute(_SCHEMA)


def get_token(slack_user_id: str, path: Optional[str] = None) -> Optional[str]:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT timetrack_token FROM employees WHERE slack_user_id = ?",
            (slack_user_id,),
        ).fetchone()
    return row["timetrack_token"] if row else None


def put_token(slack_user_id: str, token: str, label: Optional[str] = None, path: Optional[str] = None) -> None:
    """Registers an employee, or replaces their token if they already exist."""
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO employees (slack_user_id, timetrack_token, label)
            VALUES (?, ?, ?)
            ON CONFLICT(slack_user_id) DO UPDATE SET
                timetrack_token = excluded.timetrack_token,
                label = COALESCE(excluded.label, employees.label)
            """,
            (slack_user_id, token, label),
        )


def delete_employee(slack_user_id: str, path: Optional[str] = None) -> bool:
    with _connect(path) as connection:
        cursor = connection.execute("DELETE FROM employees WHERE slack_user_id = ?", (slack_user_id,))
    return cursor.rowcount > 0


def list_employees(path: Optional[str] = None) -> list[sqlite3.Row]:
    """Returns registered employees without their tokens."""
    with _connect(path) as connection:
        return connection.execute(
            "SELECT slack_user_id, label FROM employees ORDER BY slack_user_id"
        ).fetchall()
