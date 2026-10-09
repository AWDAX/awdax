"""Listing pages to rows: tables from raw HTML and the per-source LLM listing extract (from scraper.py)."""

from __future__ import annotations

import logging
import os
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from discovery import fetch_html
from inspector import ScrapePlan
from reasoning import ScrapeIntent
from url_guard import host_is

logger = logging.getLogger(__name__)

from plan_scraper import PlanDrivenScraper  # noqa: E402


def _strip_html_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


class _TableState:
    """One <table> being read: finished rows, the row and cell in progress, and cells carried down by rowspan."""

    def __init__(self) -> None:
        self.rows: list[list[tuple[str, bool]]] = []  # (text, is_header_cell)
        self.row: list[tuple[str, bool]] | None = None
        self.cell: list[str] | None = None
        self.cell_is_th = False
        self.cell_span = (1, 1)  # colspan, rowspan
        self.carry: dict[int, list[Any]] = {}  # column -> [rows still to fill, text, is_th]


class _TableParser(HTMLParser):
    """HTML tables as grids. Unlike a regular expression it keeps empty cells (so a value never slides under the wrong
    header), reads a row that starts with a header cell as data, expands colspan/rowspan, and handles nested tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict[str, Any]] = []
        self._stack: list[_TableState] = []
        self._skip = 0

    @staticmethod
    def _int(value: str | None) -> int:
        try:
            return max(1, min(int(str(value or "1").strip()), 50))
        except ValueError:
            return 1

    def _fill_carried(self, t: _TableState) -> None:
        """Cells carried down from a rowspan above, at the start of the new row or between cells."""
        assert t.row is not None
        while len(t.row) in t.carry:
            col = len(t.row)
            left, text, is_th = t.carry[col]
            t.row.append((text, is_th))
            if left <= 1:
                del t.carry[col]
            else:
                t.carry[col][0] = left - 1

    def _close_cell(self, t: _TableState) -> None:
        if t.cell is None or t.row is None:
            t.cell = None
            return
        self._fill_carried(t)
        text = _strip_html_tags(" ".join(t.cell))
        col = len(t.row)
        colspan, rowspan = t.cell_span
        t.row.append((text, t.cell_is_th))
        t.row.extend(("", t.cell_is_th) for _ in range(colspan - 1))
        if rowspan > 1:
            for k in range(colspan):
                t.carry[col + k] = [rowspan - 1, text if k == 0 else "", t.cell_is_th]
        t.cell = None

    def _close_row(self, t: _TableState) -> None:
        self._close_cell(t)
        if t.row is not None:
            self._fill_carried(t)
            if any(text for text, _ in t.row):
                t.rows.append(t.row)
        t.row = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag == "table":
            self._stack.append(_TableState())
        elif self._stack:
            t = self._stack[-1]
            if tag == "tr":
                self._close_row(t)
                t.row = []
                self._fill_carried(t)
            elif tag in ("td", "th"):
                if t.row is None:  # a cell with no <tr>: the browser starts a row for it
                    t.row = []
                self._close_cell(t)
                a = dict(attrs)
                t.cell, t.cell_is_th = [], tag == "th"
                t.cell_span = (self._int(a.get("colspan")), self._int(a.get("rowspan")))
            elif tag in ("br", "p", "li") and t.cell is not None:
                t.cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._stack:
            self._close_cell(self._stack[-1])
        elif tag == "tr" and self._stack:
            self._close_row(self._stack[-1])
        elif tag == "table" and self._stack:
            t = self._stack.pop()
            self._close_row(t)
            table = _finish_table(t.rows)
            if table:
                self.tables.append(table)

    def handle_data(self, data: str) -> None:
        if self._skip or not self._stack:
            return
        t = self._stack[-1]
        if t.cell is not None:
            t.cell.append(data)

    def finish(self) -> None:
        """The page ended with tables still open (a cut-off download, a missing </table>): close them as a browser does."""
        while self._stack:
            t = self._stack.pop()
            self._close_row(t)
            table = _finish_table(t.rows)
            if table:
                self.tables.append(table)


def _finish_table(rows: list[list[tuple[str, bool]]]) -> dict[str, Any] | None:
    """headers + data rows. The header is the first row made only of header cells; a row that mixes a header cell and
    data cells (a row label, then values) is data."""
    headers: list[str] = []
    data = rows
    if rows and all(is_th for _, is_th in rows[0]):
        headers = [text for text, _ in rows[0]]
        data = rows[1:]
    if not any(headers):
        headers = []
    body = [[text for text, _ in row] for row in data]
    return {"headers": headers, "rows": body} if headers or body else None


def extract_tables_from_html(html: str) -> list[dict[str, Any]]:
    """Every table on the page as {"headers": [...], "rows": [[...]]}, in the order they close (a nested table before the
    one holding it). Cells keep their position: an empty one is "", never removed."""
    parser = _TableParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # a page that breaks the parser still gives the tables read so far
        logger.debug("table parse stopped early")
    parser.finish()
    return parser.tables


def table_to_text(table: dict[str, Any], *, max_chars: int, max_cell: int = 160) -> tuple[str, int]:
    """A table as compact text, one row a line with " | " between cells, within `max_chars`. Returns (text, rows shown).
    Far cheaper for the model than the same table as flattened page text, and the rows stay rows."""
    lines: list[str] = []
    used = 0
    headers = table.get("headers") or []
    if headers:
        line = " | ".join(h[:max_cell] for h in headers)
        lines.append(line)
        used += len(line) + 1
    shown = 0
    for row in table.get("rows") or []:
        line = " | ".join(c[:max_cell] for c in row)
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
        shown += 1
    return "\n".join(lines), shown


_NEXT_LABELS = {"next", "next page", "next ›", "next »", "next >", "›", "»", ">", ">>", "→", "older", "older posts", "next →"}


class _LinkCollector(HTMLParser):
    """Every link of a page with the words a person would read on it (text, aria-label, title) and its rel."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []  # href, rel, label
        self._open: list[Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "link" and a.get("href") and "next" in a.get("rel", "").lower().split():
            self.links.append((a["href"], a.get("rel", ""), "next"))
        elif tag == "a" and a.get("href"):
            self._open = [a["href"], a.get("rel", ""), [a.get("aria-label", ""), a.get("title", "")]]

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._open is not None:
            href, rel, parts = self._open
            self.links.append((href, rel, " ".join(" ".join(parts).split())))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open[2].append(data)


def find_next_page_url(html: str, base_url: str) -> str | None:
    """The address of the next page of a paginated listing, or None. Looks for what the page itself declares (rel="next"),
    then for a link people read as "Next" (or an arrow). Only a page on the same site, and never the page we are on."""
    collector = _LinkCollector()
    try:
        collector.feed(html or "")
        collector.close()
    except Exception:
        logger.debug("link scan stopped early")
    own = (urlsplit(base_url).hostname or "").lower().removeprefix("www.")

    def usable(href: str) -> str | None:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return None
        absolute = urljoin(base_url, href).split("#")[0]
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or (parts.hostname or "").lower().removeprefix("www.") != own:
            return None
        return None if absolute.rstrip("/") == base_url.split("#")[0].rstrip("/") else absolute

    for href, rel, _ in collector.links:
        if "next" in rel.lower().split() and (found := usable(href)):
            return found
    for href, _, label in collector.links:
        if label.lower() in _NEXT_LABELS or re.fullmatch(r"(?:go to )?next(?: page)?", label.lower()):
            if found := usable(href):
                return found
    return None


def _finalize_extract_rows(
    rows: list[dict[str, Any]],
    plan: ScrapePlan,
    *,
    intent: ScrapeIntent | None = None,
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    id_field = plan.id_field or "car_name"
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        brand = str(row.get("brand") or "").strip()
        car = str(row.get("car_name") or row.get("name") or "").strip()
        first = str(row.get(columns[0]) or "").strip() if columns else ""
        ext = (f"{brand}|{car}" if brand and car else "") or row.get(id_field) or car or first or row.get("_row_key") or ""
        if not ext:
            row[id_field] = f"row_{i}"
        elif not row.get(id_field):
            row[id_field] = str(ext)[:120]
        row.setdefault("PDF_URL", "")
        row.setdefault("PDF_Text", "")
        out.append(row)

    # One page lists each item once, so two rows with the same id are two items whose id column is not unique (a date, a
    # category). Keyed by it, the store kept one row per date: 50 debates of 5 sittings became 5. Each such row is told
    # apart by all of its values instead.
    from table_merge import row_value_key

    seen: dict[str, int] = {}
    for row in out:
        key = str(row.get(id_field) or "")
        seen[key] = seen.get(key, 0) + 1
    for row in out:
        if seen.get(str(row.get(id_field) or ""), 0) > 1:
            row["_uid"] = f"{row.get(id_field)}|{row_value_key(row, columns or [])}"

    from row_quality import filter_vehicle_rows, intent_expects_priced_catalog, topic_is_vehicles

    cols = columns or []
    raw, topic = (intent.raw_prompt, intent.topic) if intent else ("", "")
    # The headline, length and price rules are for vehicle catalogs only (as in scraper._on_row): without the flag a long
    # title of any other topic (a debate, a quote, a news item) was dropped as "not a model name".
    return filter_vehicle_rows(
        out, cols or None, catalog_with_prices=bool(intent and intent_expects_priced_catalog(raw, topic)), vehicle=topic_is_vehicles(raw, topic)
    )


def _extract_listing_rows(
    html: str,
    intent: ScrapeIntent,
    schema: dict[str, Any],
    *,
    page_url: str,
    plan: ScrapePlan,
) -> list[dict[str, Any]]:
    columns = schema.get("columns") or []
    if not columns:
        return []
    from gemini_scrape import gemini_extract_rows_from_page

    rows = gemini_extract_rows_from_page(
        html,
        intent,
        columns,
        page_url=page_url,
        source_name=plan.source_name,
        column_labels=schema.get("column_labels"),
    )
    return _finalize_extract_rows(rows, plan, intent=intent, columns=columns)


def _is_regulatory_table_plan(plan: ScrapePlan) -> bool:
    url = (plan.entry_url or plan.source_url or "").lower()
    return plan.table_selector == "#gvGazetteList" or host_is(url, "egazette.gov.in")


def visible_text_length(html: str) -> int:
    """How much text a reader would see on the page (scripts, styles and tags removed)."""
    body = re.sub(r"<(script|style|noscript|template)\b[^>]*>.*?</\1>", " ", html or "", flags=re.I | re.S)
    return len(_strip_html_tags(body))


_APP_STATE = re.compile(
    r"<script\b[^>]*(?:id=[\"'](?:__NEXT_DATA__|__NUXT_DATA__|ng-state|serverApp-state)[\"']|type=[\"']application/json[\"'])[^>]*>.*?</script>",
    re.I | re.S,
)


def strip_app_state(html: str) -> str:
    """The page without the JSON blobs a JavaScript app boots from (Next.js, Nuxt, Angular transfer state)."""
    return _APP_STATE.sub(" ", html or "")


def needs_browser(html: str) -> bool:
    """True for a page whose plain HTML is an app shell: lots of markup and script, almost no text. Its records are filled in
    by JavaScript after load (Next.js, Angular, React sites such as government portals), so only a rendered page has them.
    The shell may even carry placeholder data the app replaces on load, so it must not be read as the page's content."""
    size = len(html or "")
    if size < 5000:
        return False
    text = visible_text_length(html)
    return text < 4000 and text / size < 0.02


def _fetch_html_for_gemini(
    plan: ScrapePlan,
    source_url: str,
    *,
    scroll_listing: bool,
    job_id: str = "",
    fetched: dict[str, Any] | None = None,
) -> str:
    """The page as the model should read it: one plain request first (or `fetched`, when the caller already made it); the
    browser when the listing needs scrolling or the plain HTML is only a JavaScript shell. A failed plain request is
    recorded in the run's failed-links dataset."""
    fetched = fetched if fetched is not None else fetch_html(source_url)
    html = fetched.get("html") or ""
    if job_id:
        import url_access

        url_access.record_probe(job_id, source_url, fetched, stage=url_access.SCRAPE)
    render = scroll_listing or needs_browser(html)
    if not render:
        return html

    scraper = PlanDrivenScraper(plan, fast_mode=os.getenv("SCRAPE_FAST", "1") == "1")
    scraper.setup_driver()
    try:
        scraper.open_entry()
        if scroll_listing:
            from listing_scrape import selenium_scroll_and_get_html

            return selenium_scroll_and_get_html(scraper.driver) or scraper.driver.page_source or html
        rendered = scraper.driver.page_source or ""
        if visible_text_length(rendered) <= visible_text_length(html):
            return html
        # The app's start-up data stays in the rendered page but can be placeholder rows the app replaces on load (one
        # government portal ships sample records with a dummy PDF link). What the page shows is the truth: read only that.
        return strip_app_state(rendered)
    except Exception as e:
        logger.warning("Rendering %s failed (%s); reading its plain HTML", source_url, e)
        return html
    finally:
        scraper.quit()


def _should_exhaust_listing(url: str, intent: ScrapeIntent) -> bool:
    from listing_sources import intent_wants_ev_catalog, is_aggregator_listing_url

    if is_aggregator_listing_url(url):
        return True
    return intent_wants_ev_catalog(intent) and any(
        h in (url or "").lower() for h in ("carwale", "cardekho", "91wheels", "zigwheels", "wikipedia.org/wiki")
    )
