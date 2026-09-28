"""Application configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./awdax.db")
    redis_url: str | None = os.getenv("REDIS_URL")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    # Tried in order when gemini_model is overloaded, out of quota or retired. Free-tier models only.
    gemini_fallback_models: tuple[str, ...] = tuple(
        m.strip()
        for m in os.getenv(
            "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3-flash-preview,gemini-3.1-flash-lite"
        ).split(",")
        if m.strip()
    )
    min_validated_sources: int = int(os.getenv("MIN_VALIDATED_SOURCES", "3"))
    max_sources_to_inspect: int = int(os.getenv("MAX_SOURCES_TO_INSPECT", "10"))
    max_discovery_search_rounds: int = int(os.getenv("MAX_DISCOVERY_SEARCH_ROUNDS", "8"))
    max_discovery_attempts: int = int(os.getenv("MAX_DISCOVERY_ATTEMPTS", "12"))
    max_total_urls_inspected: int = int(os.getenv("MAX_TOTAL_URLS_INSPECTED", "36"))
    browser_timeout_ms: int = int(os.getenv("BROWSER_TIMEOUT_MS", "25000"))
    browser_max_related_links: int = int(os.getenv("BROWSER_MAX_RELATED_LINKS", "4"))
    http_probe_timeout: float = float(os.getenv("HTTP_PROBE_TIMEOUT", "12"))
    host: str = os.getenv("AWDAX_HOST", "0.0.0.0")
    port: int = int(os.getenv("AWDAX_PORT", "8000"))
    live_refresh_interval_seconds: int = int(os.getenv("LIVE_REFRESH_INTERVAL_SECONDS", "300"))
    live_error_retry_seconds: int = int(os.getenv("LIVE_ERROR_RETRY_SECONDS", "60"))


settings = Settings()
