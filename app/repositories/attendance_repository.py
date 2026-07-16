from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import AttendanceLog
from app.schemas.schemas import AttendanceLogCreate

class AttendanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_log_for_day(self, employee_id: int, day: date) -> Optional[AttendanceLog]:
        # Start and end of the day
        start_of_day = datetime.combine(day, datetime.min.time())
        end_of_day = datetime.combine(day, datetime.max.time())
        
        result = await self.db.execute(
            select(AttendanceLog).where(
                and_(
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.date >= start_of_day,
                    AttendanceLog.date <= end_of_day,
                    AttendanceLog.status == "success"
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_log_by_event_id(self, slack_event_id: str) -> Optional[AttendanceLog]:
        result = await self.db.execute(
            select(AttendanceLog).where(AttendanceLog.slack_event_id == slack_event_id)
        )
        return result.scalar_one_or_none()

    async def get_active_log_for_day(self, employee_id: int, day: date) -> Optional[AttendanceLog]:
        """
        Returns the open session (successfully started, not yet ended) for
        an employee on a given day -- the row a Stop request should close.
        Returns None if the employee never successfully started today, or
        already stopped today (callers distinguish these two cases).
        """
        start_of_day = datetime.combine(day, datetime.min.time())
        end_of_day = datetime.combine(day, datetime.max.time())

        result = await self.db.execute(
            select(AttendanceLog).where(
                and_(
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.date >= start_of_day,
                    AttendanceLog.date <= end_of_day,
                    AttendanceLog.status == "success",
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_log_by_stop_event_id(self, stop_slack_event_id: str) -> Optional[AttendanceLog]:
        result = await self.db.execute(
            select(AttendanceLog).where(AttendanceLog.stop_slack_event_id == stop_slack_event_id)
        )
        return result.scalar_one_or_none()

    async def update_log(self, log: AttendanceLog, **fields) -> AttendanceLog:
        for key, value in fields.items():
            setattr(log, key, value)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def create_log(self, log_in: AttendanceLogCreate) -> AttendanceLog:
        db_log = AttendanceLog(**log_in.model_dump())
        self.db.add(db_log)
        await self.db.commit()
        await self.db.refresh(db_log)
        return db_log

    async def list_logs(self, skip: int = 0, limit: int = 100) -> List[AttendanceLog]:
        result = await self.db.execute(
            select(AttendanceLog).order_by(AttendanceLog.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
