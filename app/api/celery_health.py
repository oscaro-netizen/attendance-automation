from fastapi import APIRouter, HTTPException
from celery.result import AsyncResult
from app.workers.celery_worker import celery_app
from loguru import logger

router = APIRouter()

@router.get("/celery-health")
async def celery_health_check():
    try:
        # Ping the Celery worker to check if it's alive
        # This sends a control command and waits for a reply
        # Timeout is set to a low value to quickly detect unresponsive workers
        result = celery_app.control.ping(timeout=1, destination=["celery@%h"])
        if not result:
            raise HTTPException(status_code=503, detail="Celery worker not responding")
        
        # Optionally, check if a test task can be executed
        # This is more robust but adds overhead
        # task = celery_app.send_task("celery.ping")
        # response = task.get(timeout=1)
        # if response != "pong":
        #     raise HTTPException(status_code=503, detail="Celery test task failed")
            
        logger.info("Celery worker health check successful")
        return {"status": "celery_healthy"}
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Celery health check failed: {e}")
