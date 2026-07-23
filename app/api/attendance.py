from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.schemas import AttendanceLog
from app.workers.celery_worker import process_attendance_task

router = APIRouter()


@router.get("/attendance", response_model=List[AttendanceLog])
async def read_attendance_logs(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    repo = AttendanceRepository(db)
    return await repo.list_logs(skip=skip, limit=limit)


@router.post("/attendance/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_attendance(employee_id: int, db: AsyncSession = Depends(get_db)):
    """
    Re-queues attendance automation for an employee.

    No `slack_event_id` is passed: this is a deliberate manual re-run, so it must
    not be suppressed by the idempotency guard that protects against Slack
    redeliveries. The service's "already started today" check still prevents a
    duplicate workday start.
    """
    employee = await EmployeeRepository(db).get_by_id(employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    task = process_attendance_task.delay(employee.slack_user_id, None, None)
    logger.info(f"Manually re-queued attendance for employee_id={employee_id} as task {task.id}")
    return {"message": f"Retry queued for employee {employee_id}", "task_id": task.id}


@router.get("/logs", response_model=List[AttendanceLog])
async def get_all_logs(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    repo = AttendanceRepository(db)
    return await repo.list_logs(skip=skip, limit=limit)
