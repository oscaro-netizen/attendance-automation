from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.database.session import get_db
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.schemas import EmployeeCreate, EmployeeResponse

# Admin-only: these endpoints accept plaintext MarsOS passwords and expose the
# roster of employees along with their MarsOS identifiers.
router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(employee: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    repo = EmployeeRepository(db)
    if await repo.get_by_slack_id(employee.slack_user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee with this Slack ID already registered",
        )
    return await repo.create(employee)


@router.get("/employees", response_model=List[EmployeeResponse])
async def read_employees(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    repo = EmployeeRepository(db)
    return await repo.list(skip=skip, limit=limit)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def read_employee(employee_id: int, db: AsyncSession = Depends(get_db)):
    repo = EmployeeRepository(db)
    employee = await repo.get_by_id(employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return employee
