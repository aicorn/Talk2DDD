from typing import List
import json
from pydantic import field_validator
from pydantic_settings import BaseSettings


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
    MINIMAX_API_KEY: str = ""
    MINIMAX_MODEL: str = "MiniMax-M1"
    MINIMAX_BASE_URL: str = "https://api.minimaxi.chat/v1"

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                try:
                    parsed = json.loads(v)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"ALLOWED_ORIGINS must be a JSON array or comma-separated string, got: {v!r}"
                    ) from exc
                if not isinstance(parsed, list) or not all(isinstance(i, str) for i in parsed):
                    raise ValueError(
                        f"ALLOWED_ORIGINS must be a JSON array of strings, got: {type(parsed).__name__} {parsed!r}"
                    )
                return parsed
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
