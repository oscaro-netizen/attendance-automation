from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey, Boolean, Float, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Employee(Base):
    __tablename__ = "employees"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    slack_user_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    slack_username: Mapped[str] = mapped_column(String(100))
    marsos_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    marsos_employee_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    marsos_password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    attendance_logs: Mapped[List["AttendanceLog"]] = relationship(back_populates="employee")

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    
    id: Mapped[int] = mapped_column(primary_key=True)
<<<<<<< HEAD
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    date: Mapped[datetime] = mapped_column(DateTime, index=True)
    slack_event_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True) # For idempotency
    started: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50)) # success, duplicate, failure
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    employee: Mapped["Employee"] = relationship(back_populates="attendance_logs")
=======

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        index=True,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime,
        index=True,
    )

    slack_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        index=True,
    )  # For idempotency

    started: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(String(50))  # success, duplicate, failure

    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    response_time: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    # --- Stop / clock-out lifecycle (Phase 2) ---------------------------
    # Mirrors the started/status/failure_reason/response_time fields above,
    # but for the end-of-day DM stop action. Kept on the same row (one row
    # per employee per day) rather than a second table, since a day's
    # attendance is a single start/stop lifecycle, not an independent event.

    ended: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    stop_slack_event_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=True,
    )  # Separate from slack_event_id (the Start event) for stop idempotency

    stop_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )  # success, duplicate, failure, not_started

    stop_failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    stop_response_time: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )

    employee: Mapped["Employee"] = relationship(
        back_populates="attendance_logs"
    )
>>>>>>> ec120ac (Implement attendance stop workflow and improve Slack event processing)
