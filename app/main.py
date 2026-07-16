from fastapi import FastAPI
from app.api import slack_events, health, employees, attendance, celery_health
from app.core.config import settings
from app.middleware.security import AuditLogMiddleware

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_middleware(AuditLogMiddleware)

app.include_router(health.router, tags=["health"])
app.include_router(slack_events.router, prefix=settings.API_V1_STR, tags=["slack"])
app.include_router(employees.router, prefix=settings.API_V1_STR, tags=["employees"])
app.include_router(attendance.router, prefix=settings.API_V1_STR, tags=["attendance"])
app.include_router(celery_health.router, prefix=settings.API_V1_STR, tags=["celery_health"])

@app.get("/")
async def root():
    return {"message": "Welcome to Attendance Automation API"}
