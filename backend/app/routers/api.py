from fastapi import APIRouter

from app.routers.v1.users import router as users_router
from app.routers.v1.ai import router as ai_router
from app.routers.v1.agent import router as agent_router
from app.routers.v1.projects import router as projects_router

api_router = APIRouter()

api_router.include_router(users_router, prefix="/v1/users", tags=["users"])
api_router.include_router(ai_router, prefix="/v1/ai", tags=["ai"])
api_router.include_router(agent_router, prefix="/v1/agent", tags=["agent"])
api_router.include_router(projects_router, prefix="/v1/projects", tags=["projects"])
