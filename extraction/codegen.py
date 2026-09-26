"""Coding agent: generate a new extractor module when builtins fail."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field

from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).resolve().parent.parent / "extractors" / "generated"


class GeneratedExtractorSpec(BaseModel):
    module_name: str = Field(description="snake_case module name")
    description: str
    source_code: str = Field(description="Full Python module implementing extract(html, url).")


_PROMPT = """Write a Python module for AWDAX that extracts structured rows from HTML.

User goal: {user_goal}
URL: {url}
Failure: {reason}

Requirements:
- Only use: re, json, bs4 (BeautifulSoup)
- Define: def extract(html: str, url: str) -> list[dict[str, str]]
- Return up to 200 rows with string values
- Focus on the user's goal (models, prices, etc.)
- No network calls, no file I/O, no imports besides re, json, bs4

Return JSON with module_name, description, source_code (full file as string).
"""


def _safe_module_name(url: str, user_goal: str) -> str:
    raw = hashlib.sha1(f"{url}|{user_goal}".encode()).hexdigest()[:10]
    return f"gen_{raw}"


def cook_extractor(user_goal: str, url: str, html_sample: str, reason: str):
    sample = html_sample[:12000]
    prompt = _PROMPT.format(user_goal=user_goal, url=url, reason=reason) + f"\n\nHTML sample:\n{sample}"
    try:
        spec = generate_json(prompt, GeneratedExtractorSpec, temperature=0.25)
    except GeminiError as exc:
        logger.warning("Codegen failed: %s", exc)
        return None, None

    name = re.sub(r"[^a-z0-9_]", "_", spec.module_name.lower()) or _safe_module_name(url, user_goal)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    path = GENERATED_DIR / f"{name}.py"
    path.write_text(spec.source_code, encoding="utf-8")
    return path, spec


def load_generated(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
