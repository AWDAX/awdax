"""Vision-assisted extraction when DOM rules fail."""

from __future__ import annotations

import base64
import json
import logging
import re

from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

from config.settings import settings
from llm import nvidia

logger = logging.getLogger(__name__)


def _rows_from_text(text: str) -> list[dict[str, str]]:
    text = (text or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return []
        payload = json.loads(match.group(0))
    rows = payload.get("rows", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
    return [{str(k): str(v) for k, v in row.items()} for row in rows if isinstance(row, dict)]


def _nvidia_rows(png: bytes, prompt: str) -> list[dict[str, str]] | None:
    """Rows from NVIDIA's vision model, or None when it can't answer (then Gemini tries)."""
    if not (settings.nvidia_api_key and settings.nvidia_vision_model):
        return None
    image = f"data:image/png;base64,{base64.b64encode(png).decode()}"
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image}},
        {"type": "text", "text": prompt},
    ]}]
    try:
        return _rows_from_text(nvidia.json_text(nvidia.chat(settings.nvidia_vision_model, messages, temperature=0.2)))
    except (nvidia.NvidiaError, json.JSONDecodeError) as exc:
        logger.warning("NVIDIA vision extract failed, trying Gemini: %s", str(exc)[:200])
        return None


def extract_with_vision(user_goal: str, url: str) -> list[dict[str, str]]:
    if not (settings.gemini_api_key or settings.nvidia_api_key):
        return []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=settings.browser_timeout_ms)
            page.wait_for_timeout(2000)
            png = page.screenshot(full_page=False, type="png")
            browser.close()
    except Exception as exc:
        logger.warning("Vision screenshot failed: %s", exc)
        return []

    prompt = (
        f"User goal: {user_goal}\n"
        "From the screenshot, extract listing data as JSON only:\n"
        '{"rows":[{"model":"","price":"","brand":""}, ...]}\n'
        "Use string values. Max 80 rows. Omit keys you cannot see."
    )
    rows = _nvidia_rows(png, prompt)
    if rows is not None or not settings.gemini_api_key:
        return rows or []
    client = genai.Client(api_key=settings.gemini_api_key)
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=png, mime_type="image/png"),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        return _rows_from_text(response.text or "")
    except Exception as exc:
        logger.warning("Vision LLM extract failed: %s", exc)
        return []
