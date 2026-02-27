"""Centralized configuration — loaded from environment variables / .env file."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # ── LLM ────────────────────────────────────────────────────────
    llm_provider: str = "gemini"  # "gemini", "anthropic", or "openai"
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = ""  # blank = use provider default

    # ── Database ───────────────────────────────────────────────────
    data_dir: str = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data"
    )
    database_url: str = ""  # blank = sqlite in data_dir

    # ── Behaviour ──────────────────────────────────────────────────
    llm_temperature: float = 0.2  # low for deterministic output
    llm_max_tokens: int = 4096
    llm_timeout: int = 60  # seconds

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        os.makedirs(self.data_dir, exist_ok=True)
        return f"sqlite:///{os.path.join(self.data_dir, 'resume_matcher.db')}"

    @property
    def resolved_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        defaults = {
            "gemini": "gemini-2.0-flash",
            "anthropic": "claude-sonnet-4-20250514",
            "openai": "gpt-4o",
        }
        return defaults.get(self.llm_provider, "gemini-2.0-flash")

    @property
    def resolved_api_key(self) -> str:
        keys = {
            "gemini": self.gemini_api_key,
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
        }
        return keys.get(self.llm_provider, "")


@lru_cache()
def get_settings() -> Settings:
    """Cached singleton — call this to get settings anywhere."""
    return Settings()
