from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "Talk2DDD API",
    }
