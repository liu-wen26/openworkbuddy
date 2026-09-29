from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Auto Grader"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/auto_grader"
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    STORAGE_ROOT: str = "/workspace/ai-auto-grader/storage"
    MAX_UPLOAD_SIZE_MB: int = 50

    # 异步任务：USE_CELERY=False 时使用 FastAPI 后台任务内联执行（无需 Redis）
    USE_CELERY: bool = False
    # 图像预处理参数
    OMR_FILL_THRESHOLD: float = 0.45  # 单个填涂块的判定阈值（0~1，越大越严格）

    LLM_PROVIDER: str = "openai"  # openai | local
    LLM_API_BASE: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_DEFAULT_MODEL: str = "gpt-4o"
    LLM_CONFIDENCE_THRESHOLD: float = 0.7

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
