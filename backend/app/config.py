from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "AptlyPilot"
    API_V1_PREFIX: str = "/api/v1"

    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    LOG_LEVEL: str = "INFO"

    POSTGRES_DB: str = "aptly_pilot"
    POSTGRES_USER: str = "aptly"
    POSTGRES_PASSWORD: str = "aptly"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    DATABASE_URL: str = "postgresql+psycopg://aptly:aptly@postgres:5432/aptly_pilot"

    SECRET_KEY: str = "change-this-secret-key-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_ALGORITHM: str = "HS256"

    REPOS_CONFIG_PATH: str = "/app/examples/repos.yaml"

    # مسیرهای داخلی پروژه
    APP_DIR: Path = Path(__file__).resolve().parent
    PROJECT_ROOT: Path = APP_DIR.parent
    SCRIPTS_DIR: Path = APP_DIR / "scripts"
    DEFAULT_SCRIPTS_FILE: Path = SCRIPTS_DIR / "aptly_default_scripts.py"
    
    # تنظیمات Worker
    WORKER_HEARTBEAT_INTERVAL_SECONDS: int = 30
    WORKER_STALE_HEARTBEAT_SECONDS: int = 300
    WORKER_POLL_INTERVAL_SECONDS: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()