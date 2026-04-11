from typing import List
import json
from pathlib import Path
from pydantic_settings import BaseSettings

# Resolve .env paths relative to this file so the app finds the right .env
# regardless of which directory uvicorn is started from.
# Priority (highest last): project root .env → backend/.env
_BACKEND_DIR = Path(__file__).resolve().parent.parent   # backend/
_PROJECT_ROOT = _BACKEND_DIR.parent                      # project root


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Talk2DDD"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://talk2ddd:password@localhost:5432/talk2ddd"

    # JWT Authentication
    SECRET_KEY: str = "change-this-secret-key-in-production-minimum-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI Provider selection: "openai", "deepseek", or "minimax"
    AI_PROVIDER: str = "openai"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4"

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"

    # MiniMax
    # Domestic China endpoint: https://api.minimax.chat/v1
    # International endpoint:  https://api.minimaxi.chat/v1
    MINIMAX_API_KEY: str = ""
    MINIMAX_MODEL: str = "MiniMax-Text-01"
    MINIMAX_BASE_URL: str = "https://api.minimax.chat/v1"

    # CORS — stored as str to prevent pydantic-settings from trying to JSON-parse
    # the value before our own validator runs (it raises SettingsError for
    # comma-separated strings when the field type is List[str]).
    # Use the `cors_origins` property to get the parsed list.
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://127.0.0.1:8080"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    @property
    def cors_origins(self) -> List[str]:
        """Return ALLOWED_ORIGINS as a list, accepting both comma-separated strings
        and JSON arrays so that any .env file format works."""
        v = self.ALLOWED_ORIGINS.strip()
        if v.startswith("["):
            try:
                parsed = json.loads(v)
                return [str(i) for i in parsed]
            except json.JSONDecodeError:
                # Fall back to comma-separated parsing if JSON is malformed
                pass
        return [o.strip() for o in v.split(",") if o.strip()]

    class Config:
        # Search the project root first, then backend/ (backend/.env takes precedence).
        # Using absolute paths means the app finds the right .env file regardless of
        # which directory uvicorn is started from.
        env_file = (str(_PROJECT_ROOT / ".env"), str(_BACKEND_DIR / ".env"))
        case_sensitive = True


settings = Settings()
