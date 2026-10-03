"""
Inspect a candidate source and produce a machine-runnable ScrapePlan.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from discovery import SourceCandidate, normalize_https, probe_https
from reasoning import ScrapeIntent, gemini_json

logger = logging.getLogger(__name__)

_NOT_FOUND_TITLE_RE = re.compile(
    r"\b(404|not found|page not found|page doesn.t exist|couldn.t find|error 404|no longer available)\b",
    re.I,
)


def page_looks_unreachable(*, http_status: int, title: str = "") -> str | None:
    """Human-readable reason when a URL should not be accepted for scraping."""
    if http_status in (404, 410):
        return f"HTTP {http_status} (page not found)"
    if 400 <= http_status < 500 and http_status not in (401, 403):
        return f"HTTP {http_status}"
    if _NOT_FOUND_TITLE_RE.search((title or "").strip()):
        return "Page title indicates not found"
    return None


def _tables_with_data(signals: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in signals.get("tables") or []:
        if not isinstance(t, dict):
            continue
        if t.get("headers") or t.get("sample_rows"):
            out.append(t)
    return out


def inspection_reject_reason(
    plan: ScrapePlan,
    *,
    https_probe: dict[str, Any],
    signals: dict[str, Any],
) -> str | None:
    """Return rejection reason, or None if the source is acceptable."""
    if os.getenv("INSPECT_ACCEPT_ZERO_ROWS", "").strip().lower() in ("1", "true", "yes"):
        return None
    status = int(https_probe.get("http_status") or 0)
    title = str(signals.get("title") or https_probe.get("title") or plan.source_name or "")
    missing = page_looks_unreachable(http_status=status, title=title)
    if missing:
        return missing
    if not https_probe.get("https_ok"):
        return str(https_probe.get("error") or "Unreachable over HTTPS")
    if plan.dry_run_rows > 0:
        return None
    if _tables_with_data(signals):
        return None
    if int(https_probe.get("table_count") or 0) > 0 and (https_probe.get("table_headers_preview") or []):
        return None
    return "No table/list data detected (dry-run 0 rows)"


def _finalize_inspection_plan(
    plan: ScrapePlan,
    *,
    https_probe: dict[str, Any],
    signals: dict[str, Any],
) -> ScrapePlan:
    reason = inspection_reject_reason(plan, https_probe=https_probe, signals=signals)
    if reason:
        plan.blocked = True
        plan.confidence = 0.0
        if reason not in plan.warnings:
            plan.warnings.append(reason)
    elif plan.dry_run_rows == 0:
        plan.warnings.append("Dry run 0 rows but page has tables; scrape may need tuning")
        plan.confidence = min(plan.confidence, 0.45)
    return plan

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@dataclass
class ScrapePlan:
    source_name: str
    entry_url: str
    listing_ready_steps: list[dict[str, Any]] = field(default_factory=list)
    table_selector: str = "table"
    column_map: dict[str, str] = field(default_factory=dict)
    id_field: str = "id"
    id_column_index: int | None = None
    pagination_type: str = "none"
    pagination_pattern: str = "Page${n}"
    detail_mode: str = "none"
    detail_click_selector: str = ""
    direct_url_template: str = ""
    stop_when_seen: bool = False
    confidence: float = 0.5
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False
    dry_run_rows: int = 0
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScrapePlan:
        return cls(
            source_name=str(data.get("source_name") or "unknown"),
            entry_url=str(data.get("entry_url") or ""),
            listing_ready_steps=list(data.get("listing_ready_steps") or []),
            table_selector=str(data.get("table_selector") or "table"),
            column_map=dict(data.get("column_map") or {}),
            id_field=str(data.get("id_field") or "id"),
            id_column_index=data.get("id_column_index"),
            pagination_type=str(data.get("pagination_type") or "none"),
            pagination_pattern=str(data.get("pagination_pattern") or "Page${n}"),
            detail_mode=str(data.get("detail_mode") or "none"),
            detail_click_selector=str(data.get("detail_click_selector") or ""),
            direct_url_template=str(data.get("direct_url_template") or ""),
            stop_when_seen=bool(data.get("stop_when_seen")),
            confidence=float(data.get("confidence") or 0.5),
            warnings=list(data.get("warnings") or []),
            blocked=bool(data.get("blocked")),
            dry_run_rows=int(data.get("dry_run_rows") or 0),
            source_url=str(data.get("source_url") or data.get("entry_url") or ""),
        )


def ai_map_table_columns(
    intent: ScrapeIntent,
    headers: list[str],
    sample_rows: list[list[str]],
    *,
    table_selector: str = "table",
) -> dict[str, Any]:
    """Use Gemini to map table headers → semantic fields and pick id column."""
    if not headers:
        return {}
    prompt = f"""You are mapping HTML table columns for web scraping.

User wants data about: {intent.topic}
Desired fields: {intent.output_fields or ["all useful columns"]}

Table CSS selector hint: {table_selector}
Headers: {json.dumps(headers)}
Sample rows: {json.dumps(sample_rows[:3])}

Return JSON object with:
- column_map: object mapping semantic snake_case field names to EXACT header text from the list
- id_field: one key from column_map to use as unique row id (or "row_index" if none)
- id_column_index: integer index of id column in headers, or null
- table_selector: best css selector if obvious else "table"

Use only header strings that appear in Headers. Include at least 3 fields when possible."""
    data = gemini_json(prompt)
    if not isinstance(data, dict):
        return {}
    return data


def egazette_preset_plan() -> ScrapePlan:
    return ScrapePlan(
        source_name="eGazette India",
        entry_url="https://egazette.gov.in",
        listing_ready_steps=[
            {"action": "click", "by": "css", "selector": "input[name='ImgMessage_OK']", "optional": True, "wait": 2},
            {"action": "click", "by": "css", "selector": "a.cancel", "optional": True, "wait": 2},
            {"action": "click", "by": "xpath", "selector": "//a[contains(normalize-space(text()), 'View All')]", "optional": True, "wait": 3},
        ],
        table_selector="#gvGazetteList",
        column_map={
            "ministry": "Ministry / Organization",
            "subject": "Subject",
            "issue_date": "Issue Date",
            "publish_date": "Publish Date",
            "gazette_id": "Gazette ID",
        },
        id_field="gazette_id",
        id_column_index=4,
        pagination_type="link_href",
        pagination_pattern="Page${n}",
        detail_mode="url_template",
        direct_url_template="https://egazette.gov.in/WriteReadData/{year}/{num}.pdf",
        stop_when_seen=False,
        confidence=1.0,
    )


def _setup_driver(headless: bool = True):
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=opts)


def _hard_blocked(html_lower: str) -> bool:
    """Only block on strong auth/captcha walls — not footer 'login' links."""
    patterns = [
        r"g-recaptcha",
        r"hcaptcha",
        r"cf-challenge",
        r"challenge-platform",
        r"id=\"captcha",
        r"class=\"[^\"]*captcha",
        r"type=\"password\"[^>]*required",
        r"sign in to continue",
        r"access denied",
    ]
    hits = sum(1 for p in patterns if re.search(p, html_lower))
    return hits >= 2


def _probe_page_selenium(url: str) -> dict[str, Any]:
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium not installed")
    driver = _setup_driver()
    signals: dict[str, Any] = {"url": url, "title": "", "tables": [], "buttons": []}
    try:
        driver.get(url)
        time.sleep(2)
        signals["title"] = driver.title
        tables = driver.find_elements(By.TAG_NAME, "table")[:8]
        for i, tbl in enumerate(tables):
            tid = tbl.get_attribute("id") or ""
            sel = f"#{tid}" if tid else f"table:nth-of-type({i + 1})"
            headers = [th.text.strip() for th in tbl.find_elements(By.TAG_NAME, "th") if th.text.strip()]
            rows = tbl.find_elements(By.TAG_NAME, "tr")
            sample = []
            for row in rows[1:4]:
                cells = [c.text.strip()[:120] for c in row.find_elements(By.TAG_NAME, "td")]
                if cells:
                    sample.append(cells)
            signals["tables"].append(
                {"id": tid or f"table_{i}", "selector": sel, "headers": headers, "sample_rows": sample}
            )
        page_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'Page$')]")
        signals["pagination_hrefs"] = [(a.get_attribute("href") or "")[:120] for a in page_links[:5]]
        body = (driver.page_source or "")[:12000].lower()
        signals["hard_blocked"] = _hard_blocked(body)
    finally:
        driver.quit()
    return signals


def _apply_ai_column_map(plan: ScrapePlan, intent: ScrapeIntent, headers: list[str], sample: list[list[str]], selector: str):
    mapping = ai_map_table_columns(intent, headers, sample, table_selector=selector)
    if mapping.get("column_map"):
        plan.column_map = dict(mapping["column_map"])
    if mapping.get("id_field"):
        plan.id_field = str(mapping["id_field"])
    if mapping.get("id_column_index") is not None:
        plan.id_column_index = int(mapping["id_column_index"])
    if mapping.get("table_selector"):
        plan.table_selector = str(mapping["table_selector"])


def _plan_from_gemini(intent: ScrapeIntent, source: SourceCandidate, signals: dict[str, Any]) -> ScrapePlan:
    https = signals.get("https_probe") or {}
    prompt = f"""Create a ScrapePlan JSON for Selenium scraping.
Do NOT set blocked=true unless hard_blocked is true in signals.
Prefer table_selector from tables[].selector with most data rows.

Keys: source_name, entry_url, listing_ready_steps, table_selector, column_map,
id_field, id_column_index, pagination_type (link_href|none), pagination_pattern,
detail_mode (none|click|url_template), direct_url_template, stop_when_seen,
confidence (0-1), warnings (array), blocked (bool).

Intent: {intent.output_fields or intent.topic}

Source: {json.dumps(source.to_dict())}

Signals:
{json.dumps(signals, indent=2)}

HTTPS preview headers: {https.get("table_headers_preview")}"""
    data = gemini_json(prompt)
    if not isinstance(data, dict):
        raise ValueError("Inspector model did not return plan object")
    data.setdefault("entry_url", source.final_url or source.url)
    data.setdefault("source_name", source.title or source.domain)
    if signals.get("hard_blocked"):
        data["blocked"] = True
    else:
        data["blocked"] = False
    plan = ScrapePlan.from_dict(data)
    plan.source_url = source.final_url or source.url

    best = signals.get("tables") or []
    if best:
        t0 = max(best, key=lambda t: len(t.get("sample_rows") or []))
        if t0.get("headers"):
            _apply_ai_column_map(plan, intent, t0["headers"], t0.get("sample_rows") or [], t0.get("selector") or plan.table_selector)
    elif https.get("table_headers_preview"):
        _apply_ai_column_map(
            plan,
            intent,
            https["table_headers_preview"],
            [],
            plan.table_selector,
        )
    return plan


def dry_run_plan(plan: ScrapePlan, intent: ScrapeIntent | None = None, max_rows: int = 20) -> int:
    if not SELENIUM_AVAILABLE:
        return 0
    from scraper import PlanDrivenScraper

    scraper = PlanDrivenScraper(plan, fast_mode=True, intent=intent)
    try:
        scraper.setup_driver()
        scraper.open_entry()
        rows = scraper.scrape_list_page(1)
        return min(len(rows), max_rows)
    except Exception as e:
        logger.warning("Dry run failed: %s", e)
        return 0
    finally:
        scraper.quit()


def inspect_source(
    intent: ScrapeIntent,
    source: SourceCandidate,
    *,
    use_preset_for_egazette: bool = True,
) -> ScrapePlan:
    url = normalize_https(source.final_url or source.url)
    if use_preset_for_egazette and "egazette.gov.in" in url:
        plan = egazette_preset_plan()
        plan.dry_run_rows = dry_run_plan(plan, intent)
        plan.source_url = url
        return plan

    https_probe = probe_https(url)
    if not https_probe.get("https_ok"):
        err = https_probe.get("error") or "unreachable"
        return ScrapePlan(
            source_name=source.title or source.domain,
            entry_url=url,
            source_url=url,
            blocked=True,
            confidence=0.0,
            warnings=[f"HTTPS probe failed: {err}"],
        )

    early = page_looks_unreachable(
        http_status=int(https_probe.get("http_status") or 0),
        title=str(https_probe.get("title") or source.title or ""),
    )
    if early:
        return ScrapePlan(
            source_name=source.title or source.domain,
            entry_url=https_probe.get("final_url") or url,
            source_url=url,
            blocked=True,
            confidence=0.0,
            warnings=[early],
        )

    signals: dict[str, Any] = {"https_probe": https_probe}
    try:
        signals.update(_probe_page_selenium(https_probe.get("final_url") or url))
    except Exception as e:
        signals["selenium_error"] = str(e)
        signals["tables"] = []
        signals["hard_blocked"] = False

    if signals.get("hard_blocked"):
        return ScrapePlan(
            source_name=source.title or source.domain,
            entry_url=https_probe.get("final_url") or url,
            source_url=url,
            blocked=True,
            confidence=0.0,
            warnings=["Hard block detected (CAPTCHA/login wall)"],
        )

    plan = _plan_from_gemini(intent, source, signals)
    plan.entry_url = https_probe.get("final_url") or url
    plan.dry_run_rows = dry_run_plan(plan, intent)

    if plan.dry_run_rows == 0 and signals.get("tables"):
        t0 = max(signals["tables"], key=lambda t: len(t.get("headers") or []))
        if t0.get("headers"):
            _apply_ai_column_map(plan, intent, t0["headers"], t0.get("sample_rows") or [], t0.get("selector") or "table")
            plan.warnings.append("Retry dry-run after AI column mapping")
            plan.dry_run_rows = dry_run_plan(plan, intent)

    return _finalize_inspection_plan(plan, https_probe=https_probe, signals=signals)


def _emit_discovery_source(on_source: Any | None, candidate: SourceCandidate, status: str, plan: ScrapePlan | None = None) -> None:
    if not on_source:
        return
    on_source({
        "url": candidate.url,
        "title": candidate.title or candidate.domain or candidate.url,
        "domain": candidate.domain,
        "origin": "search",
        "status": status,
        "reason": (plan.warnings or [""])[0] if plan and plan.blocked else "",
        "rank_score": plan.confidence if plan else None,
    })


def discover_inspected_from_queries(
    intent: ScrapeIntent,
    queries: list[Any],
    *,
    on_progress: Any | None = None,
    on_source: Any | None = None,
) -> tuple[list[SourceCandidate], list[ScrapePlan]]:
    """One search query → resolve URL (Gemini / APIs) → inspect (10 queries → up to 10 sites)."""
    from discovery import candidate_from_serp_hit
    from query_generation import GeneratedQuery
    from source_search import search_hits_for_query
    from table_merge import intent_avoid_oem_sites, is_oem_source

    def _progress(message: str) -> None:
        if on_progress:
            on_progress(message)
        logger.info("%s", message)

    parsed: list[GeneratedQuery] = []
    for q in queries:
        if isinstance(q, GeneratedQuery):
            parsed.append(q)
        elif isinstance(q, dict):
            parsed.append(GeneratedQuery.from_dict(q))
        else:
            parsed.append(GeneratedQuery(query=str(q)))

    target = min(int(intent.max_sources or 10), int(os.getenv("DISCOVERY_MAX_SOURCES", "10")))
    max_inspect_attempts = int(os.getenv("DISCOVERY_MAX_INSPECT_ATTEMPTS", "60"))
    avoid_oem = intent_avoid_oem_sites(intent)
    sources: list[SourceCandidate] = []
    plans: list[ScrapePlan] = []
    seen_urls: set[str] = set()
    all_queries: list[GeneratedQuery] = list(parsed)
    known_queries = {q.query.strip().lower() for q in all_queries if q.query.strip()}
    from query_generation import discovery_extra_queries

    for extra in discovery_extra_queries(intent, existing=known_queries):
        all_queries.append(extra)
    query_idx = 0
    inspect_attempts = 0

    from listing_sources import anchor_listings_for_intent
    from discovery import candidate_from_serp_hit as _cand_from_hit

    for anchor in anchor_listings_for_intent(intent):
        if len(plans) >= target:
            break
        if anchor.url in seen_urls:
            continue
        hit = {"url": anchor.url, "title": anchor.title, "snippet": "anchor listing"}
        candidate = _cand_from_hit(
            hit,
            search_query=f"anchor:{anchor.title}",
            source_type_hint=anchor.source_category,
        )
        if avoid_oem and is_oem_source(url=candidate.url, domain=candidate.domain):
            continue
        seen_urls.add(candidate.url)
        _emit_discovery_source(on_source, candidate, "inspecting")
        _progress(f"Anchor inspect ({len(plans) + 1}/{target}): {anchor.title}")
        try:
            plan = inspect_source(intent, candidate)
        except Exception as e:
            plan = ScrapePlan(
                source_name=candidate.title or candidate.domain,
                entry_url=candidate.final_url or candidate.url,
                source_url=candidate.url,
                blocked=True,
                confidence=0.0,
                warnings=[f"Inspect failed: {e}"],
            )
        if plan.blocked:
            _emit_discovery_source(on_source, candidate, "blocked", plan)
            reason = (plan.warnings or ["blocked"])[0]
            _progress(f"Rejected anchor: {candidate.url} — {reason}")
            continue
        sources.append(candidate)
        plans.append(plan)
        _emit_discovery_source(on_source, candidate, "validated", plan)
        _progress(f"Accepted anchor ({len(plans)}/{target}): dry-run {plan.dry_run_rows} rows")

    while len(plans) < target and inspect_attempts < max_inspect_attempts:
        if query_idx >= len(all_queries):
            refill = discovery_extra_queries(intent, existing=known_queries)
            if not refill:
                _progress(f"Discovery stopped at {len(plans)}/{target} (no more queries)")
                break
            all_queries.extend(refill)
            if query_idx >= len(all_queries):
                break

        gq = all_queries[query_idx]
        query_idx += 1
        _progress(f"Source search ({len(plans)}/{target}): {gq.query}")
        hits = search_hits_for_query(gq.query, intent, exclude_urls=seen_urls)
        if not hits:
            _progress(f"No sources found for: {gq.query}")
            continue

        accepted = False
        for hit in hits:
            if len(plans) >= target:
                break
            inspect_attempts += 1
            if inspect_attempts > max_inspect_attempts:
                break
            cand = candidate_from_serp_hit(
                hit,
                search_query=gq.query,
                source_type_hint=gq.source_type_hint,
            )
            if cand.url in seen_urls:
                continue
            if avoid_oem and is_oem_source(
                source_category=cand.source_category,
                domain=cand.domain,
                url=cand.url,
            ):
                _progress(f"Skipped OEM result: {cand.url}")
                seen_urls.add(cand.url)
                continue
            pre = page_looks_unreachable(http_status=cand.http_status, title=cand.title)
            if pre:
                _progress(f"Skipped unreachable: {cand.url} ({pre})")
                seen_urls.add(cand.url)
                continue

            seen_urls.add(cand.url)
            _emit_discovery_source(on_source, cand, "inspecting")
            _progress(f"Resolved → {cand.url}")
            _progress(f"Inspecting ({len(plans) + 1}/{target}): {cand.title or cand.url}")
            try:
                plan = inspect_source(intent, cand)
            except Exception as e:
                logger.warning("Inspect failed for %s: %s", cand.url, e)
                plan = ScrapePlan(
                    source_name=cand.title or cand.domain,
                    entry_url=cand.final_url or cand.url,
                    source_url=cand.url,
                    blocked=True,
                    confidence=0.0,
                    warnings=[f"Inspect failed: {e}"],
                )
            if plan.blocked:
                _emit_discovery_source(on_source, cand, "blocked", plan)
                reason = (plan.warnings or ["blocked"])[0]
                _progress(f"Rejected: {cand.url} — {reason}")
                continue
            sources.append(cand)
            plans.append(plan)
            _emit_discovery_source(on_source, cand, "validated", plan)
            _progress(
                f"Accepted ({len(plans)}/{target}): dry-run {plan.dry_run_rows} rows, conf {plan.confidence:.2f}"
            )
            accepted = True
            break

        if not accepted:
            _progress(f"No acceptable source for query: {gq.query}")

    if len(plans) < target:
        _progress(f"Discovery finished with {len(plans)}/{target} validated sources")

    return sources, plans


def discover_inspected_sources(
    intent: ScrapeIntent,
    *,
    on_progress: Any | None = None,
    on_source: Any | None = None,
    search_queries: list[Any] | None = None,
) -> tuple[list[SourceCandidate], list[ScrapePlan]]:
    """Discover + inspect: Google queries (if provided) or legacy candidate feed."""
    from regulatory_strategy import egazette_regulatory_discovery, intent_uses_regulatory_feed

    if intent_uses_regulatory_feed(intent):
        sources, plans = egazette_regulatory_discovery(intent, on_progress=on_progress)
        for candidate, plan in zip(sources, plans):
            _emit_discovery_source(on_source, candidate, "validated", plan)
        return sources, plans

    if search_queries:
        return discover_inspected_from_queries(intent, search_queries, on_progress=on_progress, on_source=on_source)

    from discovery import DiscoveryCandidateFeed

    max_n = min(int(intent.max_sources or 10), int(os.getenv("DISCOVERY_MAX_SOURCES", "10")))
    max_attempts = int(os.getenv("DISCOVERY_MAX_INSPECT_ATTEMPTS", "40"))
    feed = DiscoveryCandidateFeed(intent)
    sources: list[SourceCandidate] = []
    plans: list[ScrapePlan] = []
    attempts = 0

    def _progress(message: str) -> None:
        if on_progress:
            on_progress(message)
        logger.info("%s", message)

    from table_merge import intent_avoid_oem_sites, is_oem_source

    avoid_oem = intent_avoid_oem_sites(intent)

    while len(plans) < max_n and attempts < max_attempts:
        candidate = feed.next_candidate()
        if candidate is None:
            _progress(f"No more candidates ({len(plans)}/{max_n} inspected)")
            break
        if avoid_oem and is_oem_source(
            source_category=candidate.source_category,
            domain=candidate.domain,
            url=candidate.url,
        ):
            _progress(f"Skipped OEM/vendor site: {candidate.url}")
            continue
        attempts += 1
        _emit_discovery_source(on_source, candidate, "inspecting")
        _progress(f"Inspecting ({len(plans)}/{max_n}): {candidate.title or candidate.url}")
        try:
            plan = inspect_source(intent, candidate)
        except Exception as e:
            logger.warning("Inspect failed for %s: %s", candidate.url, e)
            plan = ScrapePlan(
                source_name=candidate.title or candidate.domain,
                entry_url=candidate.final_url or candidate.url,
                source_url=candidate.url,
                blocked=True,
                confidence=0.0,
                warnings=[f"Inspect failed: {e}"],
            )
        if plan.blocked:
            _emit_discovery_source(on_source, candidate, "blocked", plan)
            _progress(f"Skipped blocked: {candidate.url}")
            continue
        sources.append(candidate)
        plans.append(plan)
        _emit_discovery_source(on_source, candidate, "validated", plan)
        _progress(
            f"Accepted ({len(plans)}/{max_n}): dry-run {plan.dry_run_rows} rows, conf {plan.confidence:.2f}"
        )

    return sources, plans


def inspect_all_sources(intent: ScrapeIntent, sources: list[SourceCandidate]) -> list[ScrapePlan]:
    plans: list[ScrapePlan] = []
    for src in sources:
        try:
            plans.append(inspect_source(intent, src))
        except Exception as e:
            plans.append(
                ScrapePlan(
                    source_name=src.title or src.domain,
                    entry_url=src.final_url or src.url,
                    source_url=src.url,
                    blocked=False,
                    confidence=0.0,
                    warnings=[f"Inspect failed: {e}"],
                )
            )
    return plans


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect URL → ScrapePlan")
    parser.add_argument("--url", required=True)
    parser.add_argument("--intent", required=True)
    parser.add_argument("--out", "-o")
    args = parser.parse_args()
    with open(args.intent, encoding="utf-8") as f:
        intent = ScrapeIntent.from_dict(json.load(f))
    source = SourceCandidate(url=args.url, title=args.url)
    plan = inspect_source(intent, source)
    text = json.dumps(plan.to_dict(), indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
