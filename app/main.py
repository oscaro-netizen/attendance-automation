from fastapi import FastAPI
from app.api import slack_events, health, employees, attendance
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.include_router(health.router, tags=["health"])
app.include_router(slack_events.router, prefix=settings.API_V1_STR, tags=["slack"])
app.include_router(employees.router, prefix=settings.API_V1_STR, tags=["employees"])
app.include_router(attendance.router, prefix=settings.API_V1_STR, tags=["attendance"])

@app.get("/")
async def root():
    return {"message": "Welcome to Attendance Automation API"}
