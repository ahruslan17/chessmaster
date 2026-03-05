from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://chess:chess@localhost:5432/chess_master"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Stockfish
    stockfish_path: str = "/usr/local/bin/stockfish"
    stockfish_depth: int = 22
    stockfish_multipv: int = 5
    stockfish_time_limit: float | None = None  # seconds; if set, used instead of depth
    stockfish_threads: int = 4  # UCI Threads option for multi-core analysis

    # LLM
    llm_model: str = "gpt-4o"
    llm_api_key: str = ""
    litellm_base_url: str = ""

    # App
    app_env: str = "development"
    app_debug: bool = False


settings = Settings()
