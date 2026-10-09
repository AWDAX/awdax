"""
Inspect a candidate source and produce a machine-runnable ScrapePlan.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from discovery import SourceCandidate, fetch_html, normalize_https, probe_https
from reasoning import ScrapeIntent, gemini_json
import url_access
from robots import check_robots
from url_guard import check_browser_url, check_url, host_is

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
    if plan.off_topic:
        # Rows from such a page are about something else (Wikipedia's list of office-bearers for "debates"), so a full table
        # there is worse than none.
        return "The page is about the topic but does not list the records asked for"
    if plan.dataset_files:
        return None  # the records are in files the page offers; they are read at scrape time
    if plan.dry_run_rows > 0:
        return None
    if _tables_with_data(signals):
        return None
    if int(https_probe.get("table_count") or 0) > 0 and (https_probe.get("table_headers_preview") or []):
        return None
    return "No table/list data detected (dry-run 0 rows)"


def llm_listing_estimate(intent: ScrapeIntent, url: str, html: str | None = None) -> int:
    """How many items of what the user wants a page without any HTML table lists, by the model's reading of it. 0 when it
    holds no list of such items (an article, a login wall, a single product), when it cannot be read, or when the model is
    unavailable.

    Many catalogues, directories and product grids are made of cards, not tables. Judging a source by "has a table" threw all
    of them away; the page is read by the model later anyway, so the model is asked first whether there is anything to read."""
    try:
        if html is None:
            html = fetch_html(url).get("html") or ""
        if len(html) < 800:
            return 0
        from gemini_scrape import build_page_digest

        digest = build_page_digest(html, max_text=9000, max_table_chars=3000)
        prompt = f"""Does this web page contain a LIST of several real items that match what the user wants (a catalogue, directory,
ranking, product grid, results page: items shown as cards, rows or entries)? One article about a single thing, a login or
error page, or a page that only links elsewhere is NOT a list.

User goal: {intent.raw_prompt or intent.topic}
Page URL: {url}

Page (JSON): {json.dumps(digest, default=str)[:14000]}

Return JSON only: {{"has_listing": true or false, "estimated_items": <whole number of items visible on this page>}}"""
        data = gemini_json(prompt, temperature=0)
        if isinstance(data, dict) and data.get("has_listing") is True:
            return max(1, min(int(data.get("estimated_items") or 1), 500))
    except Exception as e:
        logger.info("Listing check failed for %s: %s", url, e)
    return 0


def rendered_row_count(signals: dict[str, Any]) -> int:
    """How many records the inspected page lists: its data feed's total, else the rows of its largest HTML table, else 0."""
    feed = signals.get("feed") or {}
    if feed:
        return int(feed.get("total") or len(feed.get("records") or []) or 0)
    try:
        from listing_extract import extract_tables_from_html

        tables = max((len(t["rows"]) for t in extract_tables_from_html(signals.get("rendered_html") or "")), default=0)
    except Exception:  # noqa: BLE001 - an unreadable page lists nothing
        tables = 0
    if tables:
        return tables
    if signals.get("ax_text"):
        import ax_reader

        return ax_reader.item_estimate(signals["ax_text"])  # cards and lists, which have no table
    return 0


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
        plan.warnings = [reason] + [w for w in plan.warnings if w != reason]
    elif plan.dry_run_rows == 0:
        plan.warnings.append("Dry run 0 rows but page has tables; scrape may need tuning")
        plan.confidence = min(plan.confidence, 0.45)
    return plan

try:
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By

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
    # The inspecting model said the page is about the topic but does not list the records asked for.
    off_topic: bool = False
    # Where discovery found the page: "research" (ranked by the web-research step), "anchor" or "search".
    origin: str = "search"
    # Data files (CSV/TSV/XLSX/JSON) the page offers: read instead of the page (dataset_files.py).
    dataset_files: list[str] = field(default_factory=list)
    # The JSON feed behind the page's JavaScript table, found while inspecting: read page by page at scrape time (data_feed.py).
    feed: dict[str, Any] | None = None
    # The page's content is built by JavaScript: read it from the browser's accessibility tree, not from its plain HTML.
    render: bool = False
    # Same-site links of the page, kept only while discovery may follow them (cleared before the plan is saved).
    page_links: list[dict[str, str]] = field(default_factory=list)

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
            off_topic=bool(data.get("off_topic")),
            origin=str(data.get("origin") or "search"),
            dataset_files=[str(u) for u in data.get("dataset_files") or []],
            feed=data.get("feed") if isinstance(data.get("feed"), dict) else None,
            render=bool(data.get("render")),
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


def page_load_seconds() -> float:
    """Selenium waits 300 s for a page's load event by default; listing sites full of ads can take that long."""
    try:
        return float(os.getenv("SELENIUM_PAGE_LOAD_SECONDS") or 45)
    except ValueError:
        return 45.0


def load_page(driver: Any, url: str) -> None:
    """Open a page; one still loading at the limit is stopped and read as it is (its tables are usually there).

    Raises UnsafeURL (before the browser is touched) for a URL that is not public http(s), and after the load when
    Chrome's own redirects ended somewhere that is not allowed.
    """
    check_url(url)
    check_robots(url)  # a page the site asks crawlers not to read is never opened
    try:
        driver.get(url)
    except TimeoutException:
        logger.info("Page load limit reached, reading it as loaded so far: %s", url)
        driver.execute_script("window.stop();")
    check_browser_url(driver)


def _setup_driver(headless: bool = True, *, capture_network: bool = False):
    import browser

    driver = browser.launch(headless=headless, capture_network=capture_network)
    driver.set_page_load_timeout(page_load_seconds())
    return driver


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


def wait_until_settled(driver: Any, *, max_s: float | None = None, min_s: float = 2.0) -> None:
    """Wait until the page stops filling in: its visible text unchanged for two checks in a row (at most `max_s`).
    JavaScript sites load their table a few seconds after the page itself; judged at a fixed 2 s they looked empty and
    their real listings were rejected as "not the records"."""
    limit = max_s if max_s is not None else float(os.getenv("PAGE_SETTLE_SECONDS", "12"))
    time.sleep(min_s)
    last, steady, waited = -1, 0, min_s
    while waited < limit:
        try:
            size = int(driver.execute_script("return (document.body && document.body.innerText || '').length") or 0)
        except Exception:  # noqa: BLE001 - a page that cannot be measured is read as it is
            return
        steady = steady + 1 if size == last and size > 0 else 0
        if steady >= 2:
            return
        last = size
        time.sleep(1)
        waited += 1


def _probe_page_selenium(url: str) -> dict[str, Any]:
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium not installed")
    driver = _setup_driver(capture_network=True)
    signals: dict[str, Any] = {"url": url, "title": "", "tables": [], "buttons": []}
    try:
        try:
            driver.execute_cdp_cmd("Network.enable", {})
        except Exception:  # noqa: BLE001 - without it the data feed is simply not looked for
            pass
        load_page(driver, url)
        wait_until_settled(driver)
        signals["title"] = driver.title
        check_browser_url(driver)  # the page may have sent the browser somewhere else while it settled
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
        source = driver.page_source or ""
        from dataset_files import find_dataset_links

        signals["dataset_links"] = find_dataset_links(source, driver.current_url or url)
        signals["rendered_html"] = source
        signals["links"] = same_site_links(source, driver.current_url or url)
        try:
            import ax_reader

            ax = ax_reader.nodes(driver)
            signals["ax_text"] = ax_reader.tree_text(ax, max_chars=60_000)
            signals["pager"] = ax_reader.pager_target(ax) is not None
        except Exception as e:  # noqa: BLE001 - the page is still judged from its HTML
            logger.info("Accessibility tree not read for %s: %s", url, e)
        try:
            import data_feed

            feed = data_feed.recognise(data_feed.capture_from_driver(driver), data_feed.visible_text(source))
            signals["feed"] = feed.to_dict() if feed else None
        except Exception as e:  # noqa: BLE001 - the page is still judged without a feed
            logger.info("Data feed check failed for %s: %s", url, e)
        body = source[:12000].lower()
        signals["hard_blocked"] = _hard_blocked(body)
    finally:
        driver.quit()
    return signals


def parent_pages(url: str) -> list[str]:
    """The pages above `url` on its site, nearest first, the site's root last: /ls/debates/x -> /ls/debates, /ls, /."""
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    segments = [s for s in parts.path.split("/") if s]
    return [urlunsplit((parts.scheme, parts.netloc, "/" + "/".join(segments[:n]), "", "")) for n in range(len(segments) - 1, -1, -1)][:3]


def same_site_links(html: str, base_url: str, *, limit: int = 120) -> list[dict[str, str]]:
    """Links of a page to other pages of the same site, with the words a person reads on them (for following a section's
    front page to the page that lists the records)."""
    from urllib.parse import urljoin, urlsplit

    host = (urlsplit(base_url).hostname or "").lower().removeprefix("www.")
    here = base_url.split("#")[0].rstrip("/")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, inner in re.findall(r"""<a\b[^>]*\bhref\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", html or "", re.I | re.S):
        link = urljoin(base_url, href.strip()).split("#")[0]
        parts = urlsplit(link)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower().removeprefix("www.") != host:
            continue
        if link.rstrip("/") == here or link in seen:
            continue
        text = " ".join(re.sub(r"<[^>]+>", " ", inner).split())[:80]
        seen.add(link)
        out.append({"url": link, "text": text})
        if len(out) >= limit:
            break
    return out


def links_toward_records(intent: ScrapeIntent, page_url: str, links: list[dict[str, str]], *, picks: int = 2) -> list[str]:
    """The links on a page that most likely lead to the page listing the records the user asked for, best first: what a
    person does on a section's front page (click "Debate Search"). The model chooses; word overlap when it is down."""
    if not links:
        return []
    numbered = [{"i": i, "text": link["text"], "url": link["url"]} for i, link in enumerate(links[:120])]
    prompt = f"""This page is part of a website that holds the records the user wants, but it does not list them itself.
Pick the links a person would click to reach the page that LISTS or SEARCHES those records (a search, index, listing or
data page), best first. Skip login, help, about, contact and unrelated sections.

User goal: {intent.raw_prompt or intent.topic}
Page: {page_url}
Links: {json.dumps(numbered, ensure_ascii=False)[:12000]}

Return JSON only: {{"picks": [<i>, ...]}} with at most {picks} numbers, or [] when no link fits."""
    try:
        data = gemini_json(prompt, temperature=0)
        chosen = [int(i) for i in (data.get("picks") if isinstance(data, dict) else data) or [] if str(i).isdigit()]
        return [numbered[i]["url"] for i in chosen if 0 <= i < len(numbered)][:picks]
    except Exception as e:  # noqa: BLE001 - fall back to plain word overlap
        logger.info("Link choice failed for %s: %s", page_url, e)
    words = {w for w in re.findall(r"[a-z]{4,}", (intent.raw_prompt or intent.topic).lower())}
    scored = sorted(((sum(w in (link["text"] + " " + link["url"]).lower() for w in words), link["url"]) for link in links), reverse=True)
    return [url for score, url in scored[:picks] if score > 0]


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


def _uses_selenium_scraper(plan: ScrapePlan) -> bool:
    """Only the eGazette table is still scraped with Selenium; every other source is read by the model from its page."""
    return plan.table_selector == "#gvGazetteList" or host_is(plan.entry_url or plan.source_url or "", "egazette.gov.in")


def _signals_for_prompt(signals: dict[str, Any]) -> dict[str, Any]:
    """What the plan model needs to see: tables, a text sample, a few links, the feed's shape. Not the rendered HTML and the
    full link list, which are for the code (megabytes in the prompt made this call slow and its answers unreliable)."""
    out = {k: v for k, v in signals.items() if k not in ("rendered_html", "links", "feed", "https_probe")}
    out["https_probe"] = {k: v for k, v in (signals.get("https_probe") or {}).items() if k != "dataset_links"}
    html = signals.get("rendered_html") or ""
    out.pop("ax_text", None)
    if signals.get("ax_text"):
        out["page_outline"] = signals["ax_text"][:3500]  # what a screen reader gets: roles, names, one line per row or card
    elif html:
        from data_feed import visible_text

        out["visible_text_sample"] = visible_text(html)[:2500]
    out["links_sample"] = [f"{x.get('text')} -> {x.get('url')}" for x in (signals.get("links") or [])[:25]]
    feed = signals.get("feed")
    if feed:
        out["data_feed"] = {"records_total": feed.get("total"), "sample_record": (feed.get("records") or [{}])[0]}
    return out


def _plan_from_gemini(intent: ScrapeIntent, source: SourceCandidate, signals: dict[str, Any]) -> ScrapePlan:
    https = signals.get("https_probe") or {}
    prompt = f"""Create a ScrapePlan JSON for Selenium scraping.
Do NOT set blocked=true unless hard_blocked is true in signals.
Prefer table_selector from tables[].selector with most data rows.

Keys: source_name, entry_url, listing_ready_steps, table_selector, column_map,
id_field, id_column_index, pagination_type (link_href|none), pagination_pattern,
detail_mode (none|click|url_template), direct_url_template, stop_when_seen,
confidence (0-1), warnings (array), blocked (bool),
holds_requested_records (bool): true only if this page lists the very records the user asked for (rows of them, or a
search/index of them), or offers them as downloadable data files (signals.dataset_links). A page ABOUT the topic
(history, office-bearers, an overview, code) is false.

User request: {intent.raw_prompt or intent.topic}
Intent: {intent.output_fields or intent.topic}

Source: {json.dumps(source.to_dict())}

Signals:
{json.dumps(_signals_for_prompt(signals), indent=2, default=str)}

HTTPS preview headers: {https.get("table_headers_preview")}"""
    data: Any = None
    for _attempt in (1, 2):  # a malformed answer is rarely repeated
        data = gemini_json(prompt)
        if isinstance(data, list):  # the plan wrapped in a list
            data = next((d for d in data if isinstance(d, dict)), None)
        if isinstance(data, dict):
            break
    if not isinstance(data, dict):
        raise ValueError("Inspector model did not return plan object")
    data.setdefault("entry_url", source.final_url or source.url)
    data.setdefault("source_name", source.title or source.domain)
    off_topic = data.get("holds_requested_records") is False
    if signals.get("hard_blocked"):
        data["blocked"] = True
    else:
        data["blocked"] = False
    plan = ScrapePlan.from_dict(data)
    plan.source_url = source.final_url or source.url
    plan.off_topic = off_topic

    best = (signals.get("tables") or []) if _uses_selenium_scraper(plan) else []
    if best:
        t0 = max(best, key=lambda t: len(t.get("sample_rows") or []))
        if t0.get("headers"):
            _apply_ai_column_map(plan, intent, t0["headers"], t0.get("sample_rows") or [], t0.get("selector") or plan.table_selector)
    elif https.get("table_headers_preview") and _uses_selenium_scraper(plan):
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
    from plan_scraper import PlanDrivenScraper

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
    if use_preset_for_egazette and host_is(url, "egazette.gov.in"):
        plan = egazette_preset_plan()
        plan.dry_run_rows = dry_run_plan(plan, intent)
        plan.source_url = url
        return plan

    # The plain request every link gets first; a failure goes into the run's failed-links dataset (url_access).
    https_probe = probe_https(url)
    url_access.record_probe(intent.job_id, url, https_probe, stage=url_access.INSPECT)
    from dataset_files import direct_file_url, is_dataset_url

    if is_dataset_url(url) and https_probe.get("http_status") == 200:
        return ScrapePlan(
            source_name=source.title or source.domain or url,
            entry_url=url,
            source_url=url,
            confidence=0.6,
            dry_run_rows=1,
            dataset_files=[direct_file_url(url)],
            warnings=["A data file: read directly"],
        )
    if https_probe.get("blocked"):
        return ScrapePlan(
            source_name=source.title or source.domain,
            entry_url=url,
            source_url=url,
            blocked=True,
            confidence=0.0,
            warnings=[str(https_probe.get("error") or "Blocked: address not allowed")],
        )
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
        url_access.record_failure(intent.job_id, url, stage=url_access.INSPECT, outcome="captcha", reason="CAPTCHA or login wall in the browser")
        return ScrapePlan(
            source_name=source.title or source.domain,
            entry_url=https_probe.get("final_url") or url,
            source_url=url,
            blocked=True,
            confidence=0.0,
            warnings=["Hard block detected (CAPTCHA/login wall)"],
        )

    signals["dataset_links"] = list(dict.fromkeys([*(https_probe.get("dataset_links") or []), *(signals.get("dataset_links") or [])]))[:10]
    try:
        plan = _plan_from_gemini(intent, source, signals)
    except Exception as e:  # noqa: BLE001 - the page is turned down, but what the browser saw (its links) is kept
        logger.warning("Inspect failed for %s: %s", url, e)
        plan = ScrapePlan(
            source_name=source.title or source.domain,
            entry_url=https_probe.get("final_url") or url,
            source_url=url,
            blocked=True,
            confidence=0.0,
            warnings=[f"Inspect failed: {e}"],
        )
        plan.page_links = list(signals.get("links") or [])
        return plan
    plan.entry_url = https_probe.get("final_url") or url
    if signals["dataset_links"] and not plan.off_topic:
        plan.dataset_files = signals["dataset_links"][:5]
        plan.warnings.append(f"Offers {len(plan.dataset_files)} data file(s): read instead of the page")
    plan.feed = signals.get("feed")
    plain_visible = int(https_probe.get("visible_chars") or -1)
    if plain_visible >= 0 and signals.get("rendered_html"):
        from listing_extract import visible_text_length

        # JavaScript puts most of what a reader sees on the page: the browser's tree, not the plain HTML, is what to read.
        plan.render = visible_text_length(signals["rendered_html"]) > max(1500, int(plain_visible * 1.5))
    if _uses_selenium_scraper(plan):
        plan.dry_run_rows = dry_run_plan(plan, intent)
    else:
        # The page was rendered once, by the probe above: its rows are counted from that, not by opening it again.
        plan.dry_run_rows = min(rendered_row_count(signals), 20)

    if plan.dry_run_rows == 0 and not _tables_with_data(signals) and not (int(https_probe.get("table_count") or 0) > 0 and https_probe.get("table_headers_preview")):
        # No table anywhere: ask the model whether the page is a list in some other layout before giving it up.
        estimate = llm_listing_estimate(intent, plan.entry_url or url, html=signals.get("rendered_html"))
        if estimate:
            plan.warnings.append("No HTML table; the page's list is read by the AI")
            plan.dry_run_rows = min(estimate, 20)
            plan.confidence = min(plan.confidence or 0.5, 0.55)

    plan.page_links = list(signals.get("links") or [])
    return _finalize_inspection_plan(plan, https_probe=https_probe, signals=signals)


def _same_files_as(plan: ScrapePlan, accepted: list[ScrapePlan]) -> bool:
    files = set(plan.dataset_files)
    return bool(files) and any(files <= set(p.dataset_files) for p in accepted)


def _emit_discovery_source(
    on_source: Any | None, candidate: SourceCandidate, status: str, plan: ScrapePlan | None = None, origin: str = ""
) -> None:
    if not on_source:
        return
    on_source({
        "url": candidate.url,
        "title": candidate.title or candidate.domain or candidate.url,
        "domain": candidate.domain,
        "origin": origin or (plan.origin if plan else "search"),
        "status": status,
        "reason": (plan.warnings or [""])[0] if plan and plan.blocked else "",
        "rank_score": plan.confidence if plan else None,
    })


def _inspect_or_blocked(intent: ScrapeIntent, candidate: SourceCandidate) -> ScrapePlan:
    """inspect_source, with a failure turned into a blocked plan (never raises)."""
    try:
        return inspect_source(intent, candidate)
    except Exception as e:
        logger.warning("Inspect failed for %s: %s", candidate.url, e)
        return ScrapePlan(
            source_name=candidate.title or candidate.domain,
            entry_url=candidate.final_url or candidate.url,
            source_url=candidate.url,
            blocked=True,
            confidence=0.0,
            warnings=[f"Inspect failed: {e}"],
        )


def _inspect_workers() -> int:
    """How many sources discovery inspects at once. Each inspection runs its own headless Chrome and LLM call."""
    try:
        return max(1, int(os.getenv("DISCOVERY_INSPECT_WORKERS", "3")))
    except ValueError:
        return 3


def discover_inspected_from_queries(
    intent: ScrapeIntent,
    queries: list[Any],
    *,
    on_progress: Any | None = None,
    on_source: Any | None = None,
    research_sites: list[dict[str, Any]] | None = None,
) -> tuple[list[SourceCandidate], list[ScrapePlan]]:
    """
    The web-research step's ranked sites first (rank 1 first), then anchor listings, then one search query → resolve
    URL → inspect, up to DISCOVERY_MAX_SOURCES sites.

    Inspections run DISCOVERY_INSPECT_WORKERS at a time, in waves that never ask for more sites than are still
    needed; results are taken in query order. Workers only search and inspect: every progress line and source
    update is handed back and delivered on this thread, because those callbacks write the chat's session.
    """
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
    from urllib.parse import urlsplit
    import queue
    import threading

    from discovery import candidate_from_serp_hit
    from listing_sources import anchor_listings_for_intent
    from query_generation import GeneratedQuery, discovery_extra_queries
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

    target = min(int(intent.max_sources or 10), int(os.getenv("DISCOVERY_MAX_SOURCES", "6")))
    # The ranked sites and anchors are tried until `target`; the searches that follow stop once this many are accepted: more
    # sources rarely add rows, and each search costs a minute or more of browser and model time.
    enough = max(1, min(target, int(os.getenv("DISCOVERY_ENOUGH_SOURCES", "4"))))
    max_inspect_attempts = int(os.getenv("DISCOVERY_MAX_INSPECT_ATTEMPTS", "60"))
    workers = _inspect_workers()
    avoid_oem = intent_avoid_oem_sites(intent)
    sources: list[SourceCandidate] = []
    plans: list[ScrapePlan] = []
    seen_urls: set[str] = set()
    seen_lock = threading.Lock()  # guards seen_urls and attempts, shared by the workers
    attempts = [0]  # inspections started
    pending: queue.Queue = queue.Queue()
    all_queries: list[GeneratedQuery] = list(parsed)
    known_queries = {q.query.strip().lower() for q in all_queries if q.query.strip()}
    all_queries += discovery_extra_queries(intent, existing=known_queries)

    def _post_progress(message: str) -> None:
        pending.put(("progress", message))

    def _post_source(candidate: SourceCandidate, status: str, plan: ScrapePlan | None = None) -> None:
        pending.put(("source", (candidate, status, plan)))

    def _deliver() -> None:
        while True:
            try:
                kind, payload = pending.get_nowait()
            except queue.Empty:
                return
            if kind == "progress":
                _progress(payload)
            else:
                _emit_discovery_source(on_source, *payload)

    def _wave(fn: Any, items: list[Any]) -> list[Any]:
        """Run fn over items on the pool, delivering callbacks here as they arrive; results in item order."""
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="inspect") as pool:
            futures = [pool.submit(fn, item) for item in items]
            # Wait only on the ones still running: a finished future would make wait() return at once and spin.
            while running := [f for f in futures if not f.done()]:
                wait(running, timeout=0.25, return_when=FIRST_COMPLETED)
                _deliver()
        _deliver()
        return [f.result() for f in futures]

    def _inspected(candidate: SourceCandidate, origin: str = "search") -> ScrapePlan:
        """Inspect, and settle the source's card as soon as this one is done, not when its wave is."""
        if candidate.http_status in (404, 410):
            # Its plain request already said the page does not exist (and was recorded): a browser would only fail again.
            plan = ScrapePlan(
                source_name=candidate.title or candidate.domain,
                entry_url=candidate.url,
                source_url=candidate.url,
                blocked=True,
                confidence=0.0,
                warnings=[f"The page does not exist (HTTP {candidate.http_status})"],
            )
        else:
            plan = _inspect_or_blocked(intent, candidate)
        plan.origin = origin
        _post_source(candidate, "blocked" if plan.blocked else "validated", plan)
        return plan

    # First the sites the web-research step ranked (rank order), then the curated anchor listings for the intent, both
    # inspected before any search. Each joins seen_urls when it is scheduled, so one left out by the target can still be
    # found by a search.
    firsts: list[tuple[str, str, SourceCandidate, str]] = []  # (label, url asked for, candidate, origin)
    first_urls: set[str] = set()
    research = [s for s in research_sites or [] if isinstance(s, dict) and s.get("url")]
    if research:
        _progress(f"Checking the {len(research)} websites the research ranked, best first…")

        def _research_candidate(site: dict[str, Any]) -> SourceCandidate:
            label = {"title": site.get("site_name") or "", "snippet": site.get("what_it_has") or ""}
            asked = f"research #{site.get('rank')}"
            candidate = candidate_from_serp_hit({"url": site["url"], **label}, search_query=asked, job_id=intent.job_id, stage=url_access.RESEARCH)
            # The model's deep link does not exist: try the pages on the same site that Google's results cited, then the
            # page one level up (/ls/debates -> /ls), the section a person would go back to.
            tries = [*(site.get("alt_urls") or []), *parent_pages(site["url"])]
            for alt in tries:
                if candidate.http_status not in (404, 410):
                    break
                candidate = candidate_from_serp_hit({"url": alt, **label}, search_query=asked, job_id=intent.job_id, stage=url_access.RESEARCH)
            return candidate

        # One plain request per site, all at once; the order of `research` (the ranking) is kept.
        with ThreadPoolExecutor(max_workers=max(1, min(len(research), 5)), thread_name_prefix="research") as pool:
            built = list(pool.map(_research_candidate, research))
        for site, candidate in zip(research, built):
            if candidate.url in first_urls or site["url"] in first_urls:
                continue
            firsts.append((f"#{site.get('rank')} {site.get('site_name') or candidate.domain}", site["url"], candidate, "research"))
            first_urls.update((site["url"], candidate.url))
    for anchor in anchor_listings_for_intent(intent):
        if anchor.url in first_urls:
            continue
        hit = {"url": anchor.url, "title": anchor.title, "snippet": "anchor listing"}
        candidate = candidate_from_serp_hit(
            hit, search_query=f"anchor:{anchor.title}", source_type_hint=anchor.source_category, job_id=intent.job_id
        )
        if avoid_oem and is_oem_source(url=candidate.url, domain=candidate.domain):
            continue
        if candidate.url in first_urls:
            continue
        firsts.append((anchor.title, anchor.url, candidate, "anchor"))
        first_urls.update((anchor.url, candidate.url))

    next_first = 0
    while len(plans) < target and next_first < len(firsts):
        batch = firsts[next_first : next_first + min(workers, target - len(plans))]
        next_first += len(batch)
        for k, (label, asked, candidate, origin) in enumerate(batch):
            seen_urls.update((asked, candidate.url))
            _emit_discovery_source(on_source, candidate, "inspecting", origin=origin)
            kind = "Research site" if origin == "research" else "Anchor"
            _progress(f"{kind} inspect ({len(plans) + k + 1}/{target}): {label}")
        results = _wave(lambda item: _inspected(item[2], item[3]), batch)
        follow: list[tuple[str, str, SourceCandidate, str]] = []
        for (label, _, candidate, origin), plan in zip(batch, results):
            kind = "research site" if origin == "research" else "anchor"
            links, plan.page_links = plan.page_links, []
            if not plan.blocked and _same_files_as(plan, plans):
                plan.blocked = True
                plan.warnings.insert(0, "Same data files as a source already accepted")
            if plan.blocked:
                _progress(f"Rejected {kind}: {candidate.url} — {(plan.warnings or ['blocked'])[0]}")
                if origin == "research" and links and "→" not in label:
                    # The site is right but this page is its front page or an overview: go where a person would click.
                    for link in links_toward_records(intent, candidate.url, links):
                        if link in seen_urls or link in first_urls:
                            continue
                        first_urls.add(link)
                        hit = {"url": link, "title": f"{label} → page", "snippet": "followed from a research site"}
                        nxt = candidate_from_serp_hit(hit, search_query=f"research {label} link", job_id=intent.job_id, stage=url_access.RESEARCH)
                        follow.append((f"{label} → {urlsplit(link).path or link}", link, nxt, "research"))
                        _progress(f"Following {label} to {link}")
                continue
            sources.append(candidate)
            plans.append(plan)
            _progress(f"Accepted {kind} ({len(plans)}/{target}): {label} — dry-run {plan.dry_run_rows} rows")
        firsts[next_first:next_first] = follow  # tried next, before the lower-ranked sites

    def _search_and_inspect(gq: GeneratedQuery) -> tuple[SourceCandidate, ScrapePlan] | None:
        # A failure here (the search API, a probe) loses only this query, never the rest of its wave.
        try:
            return _search_and_inspect_one(gq)
        except Exception as e:
            logger.warning("Source search failed for %s: %s", gq.query, e)
            _post_progress(f"Source search failed for: {gq.query}")
            return None

    def _search_and_inspect_one(gq: GeneratedQuery) -> tuple[SourceCandidate, ScrapePlan] | None:
        """One query: its hits in order until one validates (a rejected page moves on to the next hit)."""
        _post_progress(f"Source search ({len(plans)}/{target}): {gq.query}")
        with seen_lock:
            exclude = set(seen_urls)
        hits = search_hits_for_query(gq.query, intent, exclude_urls=exclude)
        if not hits:
            _post_progress(f"No sources found for: {gq.query}")
            return None
        for hit in hits:
            cand = candidate_from_serp_hit(hit, search_query=gq.query, source_type_hint=gq.source_type_hint, job_id=intent.job_id)
            # Claim the URL (and an attempt), so a parallel query that found the same page moves on to its next hit.
            with seen_lock:
                if cand.url in seen_urls:
                    continue
                seen_urls.add(cand.url)
                if attempts[0] >= max_inspect_attempts:
                    return None
            if avoid_oem and is_oem_source(source_category=cand.source_category, domain=cand.domain, url=cand.url):
                _post_progress(f"Skipped OEM result: {cand.url}")
                continue
            pre = page_looks_unreachable(http_status=cand.http_status, title=cand.title)
            if pre:
                _post_progress(f"Skipped unreachable: {cand.url} ({pre})")
                continue
            with seen_lock:
                attempts[0] += 1
            _post_source(cand, "inspecting")
            _post_progress(f"Resolved → {cand.url}")
            _post_progress(f"Inspecting: {cand.title or cand.url}")
            plan = _inspected(cand)
            if plan.blocked:
                _post_progress(f"Rejected: {cand.url} — {(plan.warnings or ['blocked'])[0]}")
                continue
            return cand, plan
        _post_progress(f"No acceptable source for query: {gq.query}")
        return None

    # Time budget: once some source is accepted, searching on for the last few must not hold the scrape back for long.
    try:
        budget_s = float(os.getenv("DISCOVERY_MAX_SECONDS", "300"))
    except ValueError:
        budget_s = 600.0
    started = time.monotonic()
    next_query = 0
    while len(plans) < enough and attempts[0] < max_inspect_attempts:
        if plans and time.monotonic() - started > budget_s:
            _progress(f"Discovery time budget used ({int(budget_s)} s): continuing with {len(plans)} source(s)")
            break
        if next_query >= len(all_queries):
            refill = discovery_extra_queries(intent, existing=known_queries)
            if not refill:
                _progress(f"Discovery stopped at {len(plans)}/{target} (no more queries)")
                break
            all_queries += refill
        batch = all_queries[next_query : next_query + min(workers, enough - len(plans))]
        next_query += len(batch)
        for result in _wave(_search_and_inspect, batch):
            if result is None:
                continue
            # The card already settled when its inspection finished (_inspected); this keeps the log in query order.
            candidate, plan = result
            if _same_files_as(plan, plans):
                _progress(f"Skipped {candidate.url}: same data files as a source already accepted")
                continue
            sources.append(candidate)
            plans.append(plan)
            _progress(f"Accepted ({len(plans)}/{target}): dry-run {plan.dry_run_rows} rows, conf {plan.confidence:.2f}")

    if len(plans) < enough:
        _progress(f"Discovery finished with {len(plans)}/{target} validated sources")
    for plan in plans:
        plan.page_links = []  # only needed while discovering; not saved with the chat
    return sources, plans


def discover_inspected_sources(
    intent: ScrapeIntent,
    *,
    on_progress: Any | None = None,
    on_source: Any | None = None,
    search_queries: list[Any] | None = None,
    research_sites: list[dict[str, Any]] | None = None,
) -> tuple[list[SourceCandidate], list[ScrapePlan]]:
    """Discover + inspect: the research step's ranked sites, then Google queries (if provided) or the legacy feed."""
    from regulatory_strategy import egazette_regulatory_discovery, intent_uses_regulatory_feed

    if intent_uses_regulatory_feed(intent):
        sources, plans = egazette_regulatory_discovery(intent, on_progress=on_progress)
        for candidate, plan in zip(sources, plans):
            _emit_discovery_source(on_source, candidate, "validated", plan)
        return sources, plans

    if search_queries or research_sites:
        return discover_inspected_from_queries(
            intent, search_queries or [], on_progress=on_progress, on_source=on_source, research_sites=research_sites
        )

    from discovery import DiscoveryCandidateFeed

    max_n = min(int(intent.max_sources or 10), int(os.getenv("DISCOVERY_MAX_SOURCES", "6")))
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
    for plan in plans:
        plan.page_links = []
    return sources, plans
