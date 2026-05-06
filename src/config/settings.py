"""Application configuration using pydantic-settings."""

from functools import lru_cache
from enum import Enum
from pathlib import Path
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}

    # ── Environment ──
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "DEBUG"
    debug: bool = True

    # ── Database ──
    database_url: str = "postgresql+asyncpg://workflow:workflow@localhost:5432/workflow"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

    # ── API ──
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Auth ──
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ── Execution Engine ──
    workflow_timeout_seconds: int = 1800
    node_timeout_seconds: int = 300
    max_parallel_workers: int = 8
    checkpoint_enabled: bool = True

    # ── Skills ──
    skills_dir: Path = Path("skills")

    # ── Model Provider ──
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Security ──
    encryption_key: str = ""
    sandbox_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
