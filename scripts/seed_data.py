import asyncio
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import AsyncSessionLocal
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.schemas import EmployeeCreate

async def seed_employee():
    async with AsyncSessionLocal() as db:
        repo = EmployeeRepository(db)
        
        # Check if test employee already exists
        existing = await repo.get_by_slack_id("U_TEST_123")
        if existing:
            from app.utils.security import encrypt_password
            existing.marsos_password_encrypted = encrypt_password("test_password")
            await db.commit()
            print(f"Updated existing test employee password using current encryption key.")
            return

        test_employee = EmployeeCreate(
            slack_user_id="U_TEST_123",
            slack_username="test_user",
            marsos_email="test@example.com",
            marsos_employee_id="EMP_TEST_001",
            marsos_password="test_password"
        )
        
        new_emp = await repo.create(test_employee)
        print(f"Created test employee: {new_emp.marsos_email} (ID: {new_emp.id})")

if __name__ == "__main__":
    asyncio.run(seed_employee())
