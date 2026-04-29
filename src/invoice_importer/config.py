# src/invoice_importer/config.py
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Logging
    log_level: str = "INFO"

    # Database
    database_url: str

    # LLM Provider
    use_local_llm: bool = True

    # Anthropic LLM provider
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-haiku-4-5"

    # Local LLM
    llama_model_path: str
    llama_n_ctx: int = 32768
    llama_n_gpu_layers: int = -1  # -1 = all layers on GPU
    llama_seed: int = 0

    @field_validator("llama_model_path", mode="after")
    @classmethod
    def _require_absolute_model_path(cls, value: str) -> str:
        """Reject relative ``LLAMA_MODEL_PATH`` values. CWD-dependent paths
        cause obscure load failures from inside ``llama-cpp``; we want a
        loud config-time error instead."""
        path = Path(value)
        if not path.is_absolute():
            raise ValueError(
                f"LLAMA_MODEL_PATH must be an absolute path; got {value!r}. "
                f"Resolved against the current working directory it would be "
                f"{path.resolve()}, but resolution is intentionally not done "
                f"automatically — set the absolute path explicitly in .env."
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]