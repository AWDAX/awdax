"""Application configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(m.strip() for m in os.getenv(name, default).split(",") if m.strip())


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./awdax.db")
    redis_url: str | None = os.getenv("REDIS_URL")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    # Tried in order when gemini_model is overloaded, out of quota or retired. Free-tier models only.
    gemini_fallback_models: tuple[str, ...] = _csv(
        "GEMINI_FALLBACK_MODELS", "gemini-3.5-flash-lite,gemini-3-flash-preview,gemini-3.1-flash-lite"
    )
    # NVIDIA's hosted models (build.nvidia.com) are tried before Gemini when NVIDIA_API_KEY is set.
    # Free developer access is rate-limited; when it says no, calls fall through to Gemini.
    nvidia_api_key: str | None = os.getenv("NVIDIA_API_KEY")
    nvidia_base_url: str = (
        os.getenv("NVIDIA_BASE_URL") or os.getenv("NVIDIA_API_BASE") or "https://integrate.api.nvidia.com/v1"
    ).rstrip("/")
    # Ordered by what answered on 29 Sep: Ultra gave the best plans; the others were intermittently
    # overloaded (503) or slow. nemotron-nano-3-30b-a3b and llama-3.1-nemotron-70b are listed but 404.
    nvidia_models: tuple[str, ...] = _csv(
        "NVIDIA_MODELS",
        "nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning,"
        "nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-super-120b-a12b",
    )
    nvidia_vision_model: str = os.getenv("NVIDIA_VISION_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    nvidia_timeout_seconds: float = float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "90"))
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
