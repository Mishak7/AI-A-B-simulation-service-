from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Synthetic AB Preflight"
    database_url: str = "sqlite+aiosqlite:///./synthetic_ab.db"
    storage_dir: Path = Path("app/storage")
    prompt_dir: Path = Path("app/prompts")
    llm_provider: str = "mock"
    winner_threshold: float = 0.10
    real_api_key: str | None = None
    real_base_url: str = "https://api.vsellm.ru/v1"
    real_model: str = "google/gemini-2.5-flash"
    real_timeout_seconds: float = 90.0
    real_max_retries: int = 3
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    log_file: Path = Path("app/storage/simab.log")
    log_level: str = "INFO"
    log_max_bytes: int = 2_000_000
    log_backup_count: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SAB_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
