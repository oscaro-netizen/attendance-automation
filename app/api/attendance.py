from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.repositories.attendance_repository import AttendanceRepository
from app.schemas.schemas import AttendanceLog, AttendanceLogCreate
from app.workers.celery_worker import process_attendance_task
from loguru import logger

router = APIRouter()

@router.post("/attendance", response_model=AttendanceLog)
async def create_attendance_log(log: AttendanceLogCreate, db: AsyncSession = Depends(get_db)):
    repo = AttendanceRepository(db)
    return await repo.create_log(log)

@router.get("/attendance", response_model=List[AttendanceLog])
async def read_attendance_logs(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    repo = AttendanceRepository(db)
    logs = await repo.list_logs(skip=skip, limit=limit)
    return logs

@router.post("/attendance/retry")
async def retry_attendance(employee_id: int):
    # In a real scenario, you would fetch the employee's slack_user_id from the DB
    # and then re-trigger the process_attendance_task.
    # For now, we'll just log and simulate a retry.
    logger.info(f"Simulating retry for employee_id: {employee_id}")
    # Example: process_attendance_task.delay(slack_user_id_from_db)
    return {"message": f"Retry initiated for employee {employee_id}"}

@router.get("/logs", response_model=List[AttendanceLog])
async def get_all_logs(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    repo = AttendanceRepository(db)
    logs = await repo.list_logs(skip=skip, limit=limit)
    return logs
