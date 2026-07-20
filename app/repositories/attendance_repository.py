from datetime import date
from typing import List, Optional

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AttendanceLog, AttendanceStatus
from app.schemas.schemas import AttendanceLogCreate
from app.utils.time import local_day_bounds_utc


class AttendanceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_successful_start_for_day(self, employee_id: int, day: date) -> Optional[AttendanceLog]:
        """
        Returns the employee's successful start record for a local calendar day,
        if one exists.

        `date` values are stored as naive UTC, so the local day is converted to
        UTC bounds before comparison. Uses a half-open [start, end) window and
        returns the first match rather than `scalar_one_or_none()`, which raised
        `MultipleResultsFound` whenever two success rows landed on the same day.
        """
        start_utc, end_utc = local_day_bounds_utc(day)

        result = await self.db.execute(
            select(AttendanceLog)
            .where(
                and_(
                    AttendanceLog.employee_id == employee_id,
                    AttendanceLog.date >= start_utc,
                    AttendanceLog.date < end_utc,
                    AttendanceLog.status == AttendanceStatus.SUCCESS,
                )
            )
            .order_by(AttendanceLog.date.asc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_log_by_event_id(self, slack_event_id: str) -> Optional[AttendanceLog]:
        result = await self.db.execute(
            select(AttendanceLog).where(AttendanceLog.slack_event_id == slack_event_id)
        )
        return result.scalar_one_or_none()

    async def create_log(self, log_in: AttendanceLogCreate) -> Optional[AttendanceLog]:
        """
        Persists a log row.

        `slack_event_id` is unique, so a redelivered Slack event racing another
        worker can violate that constraint. That is the constraint doing its job,
        not an error worth retrying the whole task over: the conflict is absorbed
        and the already-persisted row is returned instead.
        """
        db_log = AttendanceLog(**log_in.model_dump())
        self.db.add(db_log)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            logger.info(
                f"Attendance log for slack_event_id={log_in.slack_event_id} already exists; "
                "treating as already processed"
            )
            if log_in.slack_event_id:
                return await self.get_log_by_event_id(log_in.slack_event_id)
            raise
        await self.db.refresh(db_log)
        return db_log

    async def list_logs(self, skip: int = 0, limit: int = 100) -> List[AttendanceLog]:
        result = await self.db.execute(
            select(AttendanceLog).order_by(AttendanceLog.created_at.desc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
