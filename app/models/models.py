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
