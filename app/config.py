"""
Drive → Vimeo Sync: Application configuration via pydantic-settings.
Loads from environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Google
    google_sa_key_path: str = "/etc/secrets/google-sa.json"

    # Vimeo
    vimeo_access_token: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://user:password@postgres:5432/drive_vimeo"
    database_url_sync: str = "postgresql+psycopg2://user:password@postgres:5432/drive_vimeo"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Celery
    celery_concurrency: int = 2
    scanner_interval_minutes: int = 5
    integrity_check_interval_minutes: int = 2
    vimeo_monitor_interval_minutes: int = 1

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
