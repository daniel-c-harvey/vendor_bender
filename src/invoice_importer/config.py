# src/invoice_importer/config.py
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str

    # LLM provider
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5"

    # Logging
    log_level: str = "INFO"

    # Local LLM
    llama_model_path: str
    llama_n_ctx: int = 32768
    llama_n_gpu_layers: int = -1  # -1 = all layers on GPU


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]