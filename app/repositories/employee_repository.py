from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Employee
from app.schemas.schemas import EmployeeCreate, EmployeeUpdate

class EmployeeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_slack_id(self, slack_user_id: str) -> Optional[Employee]:
        result = await self.db.execute(
            select(Employee).where(Employee.slack_user_id == slack_user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, employee_id: int) -> Optional[Employee]:
        result = await self.db.execute(
            select(Employee).where(Employee.id == employee_id)
        )
        return result.scalar_one_or_none()

    async def create(self, employee_in: EmployeeCreate) -> Employee:
        data = employee_in.model_dump()
        db_employee = Employee(**data)
        self.db.add(db_employee)
        await self.db.commit()
        await self.db.refresh(db_employee)
        return db_employee

    async def list(self, skip: int = 0, limit: int = 100) -> List[Employee]:
        result = await self.db.execute(
            select(Employee).offset(skip).limit(limit)
        )
        return list(result.scalars().all())
