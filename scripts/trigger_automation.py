import asyncio
import sys
import os
import argparse

# Add project root to sys.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from app.workers.celery_worker import run_attendance_automation
from app.database.session import AsyncSessionLocal
from app.repositories.employee_repository import EmployeeRepository

async def trigger(slack_id: str):
    print(f"--- Starting Direct Automation Trigger for Slack ID: {slack_id} ---")
    
    # Check if employee exists
    async with AsyncSessionLocal() as db:
        repo = EmployeeRepository(db)
        employee = await repo.get_by_slack_id(slack_id)
        if not employee:
            print(f"Error: No employee found with Slack ID '{slack_id}'. Run seed_data.py first.")
            return
        print(f"Found employee: {employee.marsos_email}")

    print("Executing MarsOS Playwright automation...")
    try:
        await run_attendance_automation(slack_id)
        print("--- Automation Run Completed ---")
        print("Check the database 'attendance_logs' table for results.")
    except Exception as e:
        print(f"Automation failed with error: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger MarsOS automation for a Slack user.")
    parser.add_argument("--slack-id", type=str, default="U_TEST_123", help="The Slack User ID to trigger for.")
    args = parser.parse_args()
    
    asyncio.run(trigger(args.slack_id))
