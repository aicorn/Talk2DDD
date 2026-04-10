from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.api import api_router
from app.routers.health import router as health_router


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Talk2DDD - AI-powered DDD document assistant",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    application.include_router(health_router)
    application.include_router(api_router, prefix="/api")

    @application.get("/")
    async def root():
        return {
            "message": "Welcome to Talk2DDD API",
            "version": settings.APP_VERSION,
            "docs": "/docs",
        }

    return application


app = create_application()
