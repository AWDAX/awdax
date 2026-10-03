"""LLM summaries and redline analysis for gazette notifications (from RegulatoryFeed.py)."""

import hashlib
import json
import logging
import re
from typing import Any



from llm_client import llm_available, llm_text

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AI Summariser (Gemini)
# ---------------------------------------------------------------------------

class AISummarizer:
    def __init__(self):
        self.cache: dict[str, Any] = {}

    @staticmethod
    def _cache_key(text: str, subject: str) -> str:
        return hashlib.md5(f"{subject}:{text[:1000]}".encode()).hexdigest()

    # ── structured summary ──────────────────────────────────────────
    @staticmethod
    def _normalize_industry_tags(raw) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        out = []
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
            if len(out) >= 12:
                break
        return out

    def generate_summary(self, text: str, subject: str, gazette_id: str = None) -> dict[str, Any]:
        if not text or not text.strip():
            return self._fallback(text or "", subject)
        ck = self._cache_key(text, subject)
        if ck in self.cache:
            return self.cache[ck]
        result = self._gemini_summary(text, subject)
        if result and self._validate(result):
            result["industry_tags"] = self._normalize_industry_tags(result.get("industry_tags"))
            self.cache[ck] = result
            return result
        fb = self._fallback(text, subject)
        self.cache[ck] = fb
        return fb

    def _gemini_summary(self, text: str, subject: str) -> dict | None:
        if not llm_available():
            return None
        try:
            prompt = f"""Analyze this government gazette document and provide a structured summary.

Subject: {subject}
Document Text: {text[:4000]}

Provide ONLY a valid JSON response:
{{
    "topic": "Brief topic title",
    "summary": "2-3 sentence summary",
    "key_highlights": ["Key point 1", "Key point 2", "Key point 3"],
    "legal_clauses": ["Section/Act references"],
    "states": ["List of states mentioned"],
    "market_impact": "Brief market impact assessment",
    "industry_tags": ["2-8 short labels for industries/sectors this notification materially affects, e.g. Banking & finance, Pharmaceuticals, Energy & power, Manufacturing, IT & telecom, Agriculture, Real estate, Transport & logistics, Retail & e-commerce, Environment & waste, MSME, Defence, Education. Use Title Case. Omit generic tags like Government or Public sector unless that is the sole focus."]
}}"""
            m = re.search(r"\{.*\}", llm_text(prompt).strip(), re.DOTALL)
            return json.loads(m.group()) if m else None
        except Exception as e:
            logger.error(f"Gemini summary error: {e}")
            return None

    @staticmethod
    def _validate(s: dict) -> bool:
        return all(f in s for f in ("topic", "summary", "key_highlights", "legal_clauses", "states", "market_impact"))

    @staticmethod
    def _fallback(text: str, subject: str) -> dict[str, Any]:
        tl = (text or "").lower()
        clauses = re.findall(r"[Ss]ection\s+\d+[A-Za-z]*", text)[:5]
        clauses += re.findall(r"Act,?\s+\d{4}", text)[:3]
        states_set = {
            "andhra pradesh", "assam", "bihar", "chhattisgarh", "delhi",
            "goa", "gujarat", "haryana", "jharkhand", "karnataka", "kerala",
            "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
            "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
            "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
        }
        found_states = [s.title() for s in states_set if s in tl]
        highlights = []
        if "amendment" in tl:
            highlights.append("Regulatory amendment")
        if "notification" in tl:
            highlights.append("Government notification")
        mi = "Administrative notification"
        if any(k in tl for k in ("land acquisition", "railway", "infrastructure")):
            mi = "Potential infrastructure development impact"
        elif any(k in tl for k in ("amendment", "rules", "regulations")):
            mi = "Regulatory change impact"
        ind_tags: list[str] = []
        ind_kw = [
            ("pharma", "Healthcare & pharmaceuticals"),
            ("drug", "Healthcare & pharmaceuticals"),
            ("bank", "Banking & finance"),
            ("insurance", "Insurance"),
            ("tax", "Tax & compliance"),
            ("gst", "Tax & compliance"),
            ("energy", "Energy & power"),
            ("power", "Energy & power"),
            ("coal", "Mining & natural resources"),
            ("telecom", "IT & telecom"),
            ("railway", "Transport & logistics"),
            ("aviation", "Aviation"),
            ("environment", "Environment & sustainability"),
            ("waste", "Environment & sustainability"),
            ("agriculture", "Agriculture"),
            ("msme", "MSME"),
            ("defence", "Defence"),
            ("education", "Education"),
        ]
        for kw, label in ind_kw:
            if kw in tl and label not in ind_tags:
                ind_tags.append(label)
            if len(ind_tags) >= 6:
                break
        if not ind_tags:
            ind_tags = ["General regulatory"]
        return {
            "topic": (subject or "Government Notification")[:100],
            "summary": f"Government notification regarding {subject}.",
            "key_highlights": highlights or ["Government notification"],
            "legal_clauses": clauses,
            "states": found_states[:10],
            "market_impact": mi,
            "industry_tags": ind_tags,
        }

    # ── redline analysis ────────────────────────────────────────────────
    def generate_redline_analysis(
        self, subject: str, summary_text: str = "",
        key_highlights: list = None, legal_clauses: list = None,
        market_impact: str = "", states: list = None,
        pdf_text: str = None,
    ) -> dict[str, Any] | None:
        has_pdf = pdf_text and len(pdf_text.strip()) > 50
        has_summary = summary_text and summary_text.strip()
        if not has_pdf and not has_summary:
            return None
        if not llm_available():
            return None
        try:
            parts = [f"Subject: {subject}"]
            if has_summary:
                parts.append(f"Summary: {summary_text}")
            if key_highlights:
                parts.append(f"Key Highlights: {', '.join(key_highlights)}")
            if legal_clauses:
                parts.append(f"Legal Clauses: {', '.join(legal_clauses)}")
            if market_impact:
                parts.append(f"Metadata: {market_impact}")
            if states:
                parts.append(f"States: {', '.join(states)}")
            if has_pdf:
                parts.append(f"Full Document Text:\n{pdf_text[:10000]}")
            ctx = "\n\n".join(parts)
            prompt = f"""You are a legal analyst specializing in Indian government gazette notifications.
Analyze this notification and identify regulatory or policy changes.

{ctx}

Provide ONLY valid JSON:
{{
    "change_keywords": ["list of 3-5 short change tags, prefix + for additions, - for removals"],
    "impact_tags": ["2-4 tags for who/what is impacted"],
    "redline_analysis": "Markdown explanation (3-5 paragraphs): (1) previous rule, (2) what changed, (3) who is affected, (4) deadlines/actions. Use **bold** for key terms."
}}

IMPORTANT: Always produce meaningful analysis. Never say content is unavailable."""
            m = re.search(r"\{.*\}", llm_text(prompt).strip(), re.DOTALL)
            if m:
                data = json.loads(m.group())
                bad = ["not available", "not possible", "cannot be determined", "no document"]
                if any(p in (data.get("redline_analysis", "")).lower() for p in bad):
                    return None
                if "change_keywords" in data and "impact_tags" in data and "redline_analysis" in data:
                    return data
            return None
        except Exception as e:
            logger.error(f"Redline error: {e}")
            return None
