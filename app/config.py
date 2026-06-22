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
    image_api_key: str | None = None
    image_base_url: str = "https://api.vsellm.ru/v1"
    image_model: str = "google/gemini-3-pro-image-preview"
    image_size: str = "1536x1024"
    image_quality: str = "high"
    image_input_fidelity: str = "high"
    image_edit_endpoint_path: str = "/images/edits"
    image_timeout_seconds: float = 180.0
    image_max_download_bytes: int = 50_000_000
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    log_file: Path = Path("app/storage/simab.log")
    log_level: str = "INFO"
    log_max_bytes: int = 2_000_000
    log_backup_count: int = 3
    agent_pipeline_model: str = "openai/gpt-4.1-mini"
    agent_pipeline_max_tokens: int = 8_192
    agent_pipeline_timeout_seconds: float = 120.0

    @property
    def effective_image_api_key(self) -> str | None:
        return self.image_api_key or self.real_api_key

    @property
    def image_size_is_explicit(self) -> bool:
        return self.image_size.lower() != "auto" and "image_size" in self.model_fields_set

    model_config = SettingsConfigDict(env_file=".env", env_prefix="SAB_")


@lru_cache
def get_settings() -> Settings:
    return Settings()
