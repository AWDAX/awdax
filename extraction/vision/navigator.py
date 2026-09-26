"""Vision-assisted extraction when DOM rules fail."""

from __future__ import annotations

import json
import logging
import re

from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

from config.settings import settings

logger = logging.getLogger(__name__)


def extract_with_vision(user_goal: str, url: str) -> list[dict[str, str]]:
    if not settings.gemini_api_key:
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

    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = (
        f"User goal: {user_goal}\n"
        "From the screenshot, extract listing data as JSON only:\n"
        '{"rows":[{"model":"","price":"","brand":""}, ...]}\n'
        "Use string values. Max 80 rows. Omit keys you cannot see."
    )
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
        text = (response.text or "").strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return []
            payload = json.loads(match.group(0))
        rows = payload.get("rows", payload if isinstance(payload, list) else [])
        out: list[dict[str, str]] = []
        for row in rows:
            if isinstance(row, dict):
                out.append({str(k): str(v) for k, v in row.items()})
        return out
    except Exception as exc:
        logger.warning("Vision LLM extract failed: %s", exc)
        return []
