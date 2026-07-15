from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.schemas import EmployeeResponse, EmployeeCreate, EmployeeUpdate

router = APIRouter()

@router.post("/employees", response_model=EmployeeResponse)
async def create_employee(employee: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    repo = EmployeeRepository(db)
    db_employee = await repo.get_by_slack_id(employee.slack_user_id)
    if db_employee:
        raise HTTPException(status_code=400, detail="Employee with this Slack ID already registered")
    return await repo.create(employee)

@router.get("/employees", response_model=List[EmployeeResponse])
async def read_employees(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    repo = EmployeeRepository(db)
    employees = await repo.list(skip=skip, limit=limit)
    return employees

@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def read_employee(employee_id: int, db: AsyncSession = Depends(get_db)):
    repo = EmployeeRepository(db)
    employee = await repo.get_by_id(employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee
