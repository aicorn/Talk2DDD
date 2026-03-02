from fastapi import APIRouter

from app.routers.v1.users import router as users_router

api_router = APIRouter()

api_router.include_router(users_router, prefix="/v1/users", tags=["users"])
