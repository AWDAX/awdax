"""
The data feed behind a JavaScript table.

Pages built by a JavaScript app (government portals, catalogues) fill their table from a JSON API and show one page of it
at a time; their "next" is a button, not a link, so reading the rendered page gave 10 or 50 rows of thousands. Here the
page is opened once in Chrome with network logging, the JSON response whose records are the rows on screen is picked out,
and its paging (page/size or start/rows in the address, the total in the answer) is followed with plain requests. When the
feed takes a date range and the user asked for a period, the range is sent too, so the pages read are the right ones.

Nothing is site-specific: the feed is recognised by its records matching the visible table.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

logger = logging.getLogger(__name__)

_PAGE_KEYS = ("page", "pageno", "pagenumber", "page_no", "pageindex", "page_index", "currentpage", "p")
_OFFSET_KEYS = ("start", "offset", "from", "skip", "startindex", "start_index")
_SIZE_KEYS = ("size", "rows", "limit", "pagesize", "page_size", "per_page", "perpage", "count", "length", "max", "num")
_TOTAL_KEYS = ("totalelements", "total", "totalcount", "total_count", "rowscount", "recordstotal", "totalrecords",
               "totalhits", "numfound", "total_results", "totalresults", "hits")
_FROM_DATE = re.compile(r"^(from|start|since|begin)_?date$|^date_?(from|start|begin)$|^(from|since)$", re.I)
_TO_DATE = re.compile(r"^(to|end|until|till)_?date$|^date_?(to|end|until)$|^(to|until)$", re.I)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


# --------------------------------------------------------------------------- capture


def capture_json(url: str, *, wait_s: float = 8.0) -> tuple[str, list[tuple[str, Any]]]:
    """Open `url` in headless Chrome with network logging. (rendered html, [(request url, parsed JSON body)]) for the GET
    requests that answered JSON."""
    import browser

    driver = browser.launch(capture_network=True)
    try:
        from inspector import page_load_seconds

        driver.set_page_load_timeout(page_load_seconds())
        driver.execute_cdp_cmd("Network.enable", {})
        driver.get(url)
        time.sleep(wait_s)
        return driver.page_source or "", capture_from_driver(driver)
    finally:
        driver.quit()


def capture_from_driver(driver: Any, *, max_bodies: int = 40, max_chars: int = 4_000_000) -> list[tuple[str, Any]]:
    """The JSON the page loaded so far, from a Chrome that was started with performance logging: [(request url, body)]."""
    found: dict[str, str] = {}
    try:
        entries = driver.get_log("performance")
    except Exception:  # noqa: BLE001 - logging was not switched on for this browser
        return []
    for entry in entries:
        msg = json.loads(entry.get("message") or "{}").get("message") or {}
        if msg.get("method") != "Network.responseReceived":
            continue
        resp = msg["params"].get("response") or {}
        if "json" in str(resp.get("mimeType") or "").lower() and int(resp.get("status") or 0) == 200:
            found[msg["params"]["requestId"]] = str(resp.get("url") or "")
    out: list[tuple[str, Any]] = []
    for rid, req_url in list(found.items())[:max_bodies]:
        try:
            body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid}).get("body") or ""
            if len(body) <= max_chars:
                out.append((req_url, json.loads(body)))
        except Exception:  # a body Chrome no longer holds, or not JSON after all
            continue
    return out


# --------------------------------------------------------------------------- recognise


def visible_text(html: str) -> str:
    """The text a reader sees on a rendered page (scripts, styles and the app's boot data removed)."""
    from listing_extract import _strip_html_tags, strip_app_state

    return _strip_html_tags(re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", strip_app_state(html), flags=re.I | re.S))


def find_records(obj: Any, depth: int = 0) -> tuple[list[str], list[dict[str, Any]]]:
    """(path, records): the largest list of objects in a JSON answer (each with 2+ keys)."""
    best: tuple[list[str], list[dict[str, Any]]] = ([], [])
    if depth > 4:
        return best
    if isinstance(obj, list) and len(obj) >= 2 and all(isinstance(x, dict) and len(x) >= 2 for x in obj[:20]):
        best = ([], obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            path, recs = find_records(v, depth + 1)
            if len(recs) > len(best[1]):
                best = ([str(k), *path], recs)
    return best


def _strings(record: dict[str, Any]) -> list[str]:
    return [str(v).strip() for v in record.values() if isinstance(v, (str, int, float)) and len(str(v).strip()) >= 8]


def match_share(records: list[dict[str, Any]], page_text: str) -> float:
    """Share of records with a value (8+ characters) that is visible on the page: the records are the rows on screen."""
    text = " ".join(page_text.split()).lower()
    sample = records[:30]
    if not sample:
        return 0.0
    hits = sum(1 for r in sample if any(" ".join(s.split()).lower()[:60] in text for s in _strings(r)))
    return hits / len(sample)


def visible_fields(records: list[dict[str, Any]], page_text: str) -> float:
    """How many of a record's values are on screen, on average. A table row shows several (title, date, type...); an
    entry of a filter list beside the table (a name and its count) shows one, which is how the two are told apart."""
    text = " ".join(page_text.split()).lower()
    sample = records[:30]
    if not sample:
        return 0.0
    return sum(sum(1 for s in _strings(r) if " ".join(s.split()).lower()[:60] in text) for r in sample) / len(sample)


def _get(obj: Any, path: list[str]) -> Any:
    for key in path:
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj


def _find_total(obj: Any, depth: int = 0) -> int | None:
    if not isinstance(obj, dict) or depth > 2:
        return None
    for k, v in obj.items():
        if str(k).lower() in _TOTAL_KEYS:
            if isinstance(v, dict):  # {"hits": {"total": 12}}
                inner = _find_total(v, depth + 1)
                if inner is not None:
                    return inner
            try:
                return int(str(v))
            except ValueError:
                continue
    for v in obj.values():
        if isinstance(v, dict):
            found = _find_total(v, depth + 1)
            if found is not None:
                return found
    return None


@dataclass
class Feed:
    url: str
    path: list[str]
    records: list[dict[str, Any]]
    total: int | None
    params: list[tuple[str, str]] = field(default_factory=list)
    page_key: str = ""  # page-number paging
    offset_key: str = ""  # start/offset paging
    size_key: str = ""
    size: int = 0

    def to_dict(self) -> dict[str, Any]:
        """What is needed to read the feed again later without a browser (a few sample records stay, for the date format)."""
        return {"url": self.url, "path": self.path, "records": self.records[:20], "total": self.total, "params": self.params,
                "page_key": self.page_key, "offset_key": self.offset_key, "size_key": self.size_key, "size": self.size}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Feed":
        return cls(url=str(data.get("url") or ""), path=list(data.get("path") or []), records=list(data.get("records") or []),
                   total=data.get("total"), params=[(str(k), str(v)) for k, v in data.get("params") or []],
                   page_key=str(data.get("page_key") or ""), offset_key=str(data.get("offset_key") or ""),
                   size_key=str(data.get("size_key") or ""), size=int(data.get("size") or 0))

    def page_url(self, *, page: int | None = None, offset: int | None = None, size: int | None = None,
                 extra: dict[str, str] | None = None) -> str:
        parts = urlsplit(self.url)
        values = []
        for k, v in self.params:
            if k == self.page_key and page is not None:
                v = str(page)
            elif k == self.offset_key and offset is not None:
                v = str(offset)
            elif k == self.size_key and size is not None:
                v = str(size)
            elif extra and k in extra:
                v = extra[k]
            values.append((k, v))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(values, safe="(),:/", quote_via=quote), ""))


def recognise(responses: list[tuple[str, Any]], page_text: str) -> Feed | None:
    """The response whose records are the table on screen, with its paging. None when no response matches."""
    best: tuple[float, Feed] | None = None
    for url, body in responses:
        path, records = find_records(body)
        if len(records) < 3:
            continue
        share = match_share(records, page_text)
        if share < 0.3:
            continue
        params = parse_qsl(urlsplit(url).query, keep_blank_values=True)
        feed = Feed(url=url, path=path, records=records, total=_find_total(body) if isinstance(body, dict) else None, params=params)
        for k, v in params:
            low = k.lower()
            if low in _PAGE_KEYS and v.isdigit() and not feed.page_key:
                feed.page_key = k
            elif low in _OFFSET_KEYS and v.isdigit() and not feed.offset_key:
                feed.offset_key = k
            elif low in _SIZE_KEYS and v.isdigit() and not feed.size_key:
                feed.size_key, feed.size = k, int(v)
        # The records whose rows show the most values on screen; between equals, the longer list.
        score = round(visible_fields(records, page_text), 1) * 1_000_000 + len(records)
        if best is None or score > best[0]:
            best = (score, feed)
    return best[1] if best else None


# --------------------------------------------------------------------------- dates


def _date_format(records: list[dict[str, Any]]) -> str | None:
    """How the feed writes dates (strftime), judged from its own records."""
    for r in records[:20]:
        for v in r.values():
            s = str(v).strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}(T.*)?", s):
                return "%Y-%m-%d"
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", s):
                return "%m/%d/%Y" if int(s[3:5]) > 12 else "%d/%m/%Y"
            if re.fullmatch(r"\d{2}-\d{2}-\d{4}", s):
                return "%d-%m-%Y"
    return None


def date_params(feed: Feed, start: date | None, end: date | None) -> dict[str, str]:
    """The feed's own from/to date parameters filled with the period, in the feed's date format. {} when it has none."""
    fmt = _date_format(feed.records)
    if not fmt or not (start or end):
        return {}
    out: dict[str, str] = {}
    for k, _ in feed.params:
        if start and _FROM_DATE.match(k):
            out[k] = start.strftime(fmt)
        elif end and _TO_DATE.match(k):
            out[k] = end.strftime(fmt)
    return out


# --------------------------------------------------------------------------- read


def _fetch_json(url: str, referer: str) -> Any:
    from discovery import _request_headers
    from url_guard import safe_get

    headers = {**_request_headers(), "Accept": "application/json, text/plain, */*", "Referer": referer}
    res = safe_get(url, timeout=30, headers=headers, max_bytes=20_000_000)
    if res.status_code != 200:
        raise RuntimeError(f"HTTP {res.status_code}")
    return res.json()


def _page_records(feed: Feed, body: Any) -> list[dict[str, Any]]:
    recs = _get(body, feed.path) if feed.path else body
    return [r for r in recs if isinstance(r, dict)] if isinstance(recs, list) else []


def collect(
    feed: Feed,
    *,
    referer: str,
    max_rows: int,
    period: tuple[date | None, date | None] | None = None,
    on_fail: Callable[[str, str], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Records of the feed, page after page, up to `max_rows`. Pages are read with plain requests; a page that fails ends
    the walk and keeps what was read."""
    say = log or (lambda _m: None)
    if not (feed.page_key or feed.offset_key):
        return list(feed.records[:max_rows])
    size = max(feed.size, min(_env_int("FEED_PAGE_SIZE", 100), max_rows)) if feed.size_key else feed.size or len(feed.records)
    extra = date_params(feed, *(period or (None, None)))

    def url_for(n: int, sz: int, ex: dict[str, str]) -> str:
        if feed.page_key:
            first = int(dict(feed.params)[feed.page_key])  # 0 or 1, as the page itself asked
            return feed.page_url(page=first + n, size=sz if feed.size_key else None, extra=ex)
        start = int(dict(feed.params)[feed.offset_key])
        return feed.page_url(offset=start + n * sz, size=sz if feed.size_key else None, extra=ex)

    # The first page with the larger size and the period; each falls back to the page's own value if the feed refuses it.
    body: Any = None
    for sz, ex in ((size, extra), (size, {}), (feed.size or size, {})):
        try:
            body = _fetch_json(url_for(0, sz, ex), referer)
            if _page_records(feed, body):
                size, extra = sz, ex
                break
        except Exception as e:  # noqa: BLE001 - try the next, more conservative request
            body = None
            say(f"feed refused a page ({e}); retrying with the page's own settings")
    if body is None:
        if on_fail:
            on_fail(url_for(0, feed.size or size, {}), "The data feed did not answer a plain request")
        return list(feed.records[:max_rows])
    if extra:
        say(f"data feed filtered to the requested period ({', '.join(f'{k}={v}' for k, v in extra.items())})")
    total = _find_total(body) if isinstance(body, dict) else None
    rows = _page_records(feed, body)
    seen_first = {json.dumps(rows[0], sort_keys=True, default=str)} if rows else set()
    n = 1
    max_pages = _env_int("FEED_MAX_PAGES", 50)
    while len(rows) < max_rows and n < max_pages and (total is None or len(rows) < total):
        url = url_for(n, size, extra)
        try:
            page = _page_records(feed, _fetch_json(url, referer))
        except Exception as e:  # noqa: BLE001 - one failed page ends the walk, what was read is kept
            if on_fail:
                on_fail(url, f"Data feed page failed: {e}")
            break
        if not page:
            break
        key = json.dumps(page[0], sort_keys=True, default=str)
        if key in seen_first:  # the feed ignores paging and repeats itself
            break
        seen_first.add(key)
        rows += page
        n += 1
    say(f"data feed gave {len(rows[:max_rows])} rows" + (f" of {total}" if total else ""))
    return rows[:max_rows]


# --------------------------------------------------------------------------- map to the table


def _flat(value: Any) -> str:
    """A cell value from a JSON value: lists joined, objects by their first text, "['a', 'b']" strings unpacked."""
    if isinstance(value, str):
        s = value.strip()
        if s.startswith(("[", "{")) and s.endswith(("]", "}")):
            try:
                return _flat(ast.literal_eval(s))
            except (ValueError, SyntaxError):
                try:
                    return _flat(json.loads(s))
                except ValueError:
                    return s
        return s
    if isinstance(value, list):
        return ", ".join(x for x in (_flat(v) for v in value) if x)
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, str) and v.strip() and re.search(r"name|title|label", str(k), re.I):
                return v.strip()
        return next((str(v).strip() for v in value.values() if isinstance(v, str) and v.strip()), "")
    return "" if value is None else str(value)


def column_mapping(records: list[dict[str, Any]], columns: list[str], labels: list[str], goal: str) -> dict[str, list[str]]:
    """Output column -> record keys that fill it (joined when several), chosen once by the model from sample records."""
    from reasoning import gemini_json

    keys = sorted({k for r in records[:20] for k in r})
    sample = [{k: _flat(r.get(k))[:120] for k in keys} for r in records[:3]]
    prompt = f"""Map the fields of these data records to the columns of the user's table.

User goal: {goal}
Table columns (key: meaning): {json.dumps(dict(zip(columns, labels)), ensure_ascii=False)}
Record fields with sample records: {json.dumps(sample, ensure_ascii=False)[:9000]}

For every table column give the record field(s) that hold its value, best first (several only when the value is split
across fields, such as first and last name). Use [] when no field holds it. Never invent fields.
Return JSON only: {{"mapping": {{"<column>": ["<field>", ...]}}}}"""
    try:
        data = gemini_json(prompt, temperature=0)
    except Exception as e:  # noqa: BLE001 - same-name fields below, so a busy model costs accuracy, not the rows
        logger.warning("Column mapping by the model failed (%s); matching same-name fields", e)
        data = None
    mapping = data.get("mapping") if isinstance(data, dict) else None
    out: dict[str, list[str]] = {}
    for col in columns:
        fields = (mapping or {}).get(col) or []
        out[col] = [f for f in (fields if isinstance(fields, list) else [fields]) if f in keys]
    if not any(out.values()):  # the model is down or answered nonsense: same-name fields
        norm = {re.sub(r"[^a-z0-9]", "", k.lower()): k for k in keys}
        out = {c: [norm[re.sub(r"[^a-z0-9]", "", c.lower())]] if re.sub(r"[^a-z0-9]", "", c.lower()) in norm else [] for c in columns}
    return out


def value_filters(records: list[dict[str, Any]], goal: str) -> dict[str, list[str]]:
    """Field -> accepted values when the request names specific ones (a country, a state, a category) that a field of the
    data holds: a whole-world file asked about India keeps India's rows. A filter is kept only if some record matches it,
    so a value the model misnames never empties the table."""
    from reasoning import gemini_json

    keys = sorted({k for r in records[:50] for k in r})
    examples = {k: sorted({_flat(r.get(k))[:40] for r in records[:400] if _flat(r.get(k))})[:12] for k in keys}
    prompt = f"""A data file has these fields (with example values). Does the user's request limit the rows to specific values
of a field (a named country, state, city, party, category...)? Dates and periods are handled elsewhere: ignore them.

User request: {goal}
Fields and example values: {json.dumps(examples, ensure_ascii=False)[:9000]}

Return JSON only: {{"filters": [{{"field": "<field>", "values": ["<value as written in the data>", ...]}}]}} or {{"filters": []}}."""
    try:
        data = gemini_json(prompt, temperature=0)
    except Exception as e:  # noqa: BLE001 - no filter rather than a wrong one
        logger.info("Value filter not chosen: %s", e)
        return {}
    out: dict[str, list[str]] = {}
    for f in (data.get("filters") if isinstance(data, dict) else None) or []:
        field_name, values = f.get("field") if isinstance(f, dict) else None, f.get("values") if isinstance(f, dict) else None
        if field_name in keys and isinstance(values, list) and values:
            wanted = {str(v).strip().lower() for v in values}
            if any(_flat(r.get(field_name)).lower() in wanted for r in records):
                out[field_name] = [str(v) for v in values]
    return out


def apply_value_filters(records: list[dict[str, Any]], filters: dict[str, list[str]]) -> list[dict[str, Any]]:
    for field_name, values in filters.items():
        wanted = {v.strip().lower() for v in values}
        records = [r for r in records if _flat(r.get(field_name)).lower() in wanted]
    return records


def to_rows(records: list[dict[str, Any]], mapping: dict[str, list[str]]) -> list[dict[str, Any]]:
    rows = []
    for r in records:
        row = {col: " ".join(v for v in (_flat(r.get(f)) for f in fields) if v) for col, fields in mapping.items()}
        if any(row.values()):
            rows.append(row)
    return rows


def read_feed(
    url: str,
    *,
    goal: str,
    columns: list[str],
    labels: list[str],
    period: tuple[date | None, date | None] | None = None,
    max_rows: int | None = None,
    on_fail: Callable[[str, str], None] | None = None,
    log: Callable[[str], None] | None = None,
    feed: Feed | None = None,
) -> list[dict[str, Any]] | None:
    """Rows for the table from the page's data feed, or None when the page has no feed that matches its table. `feed` is
    the one inspection already found (no browser needed); without it the page is opened once to look for it."""
    say = log or (lambda _m: None)
    if feed is None:
        try:
            html, responses = capture_json(url)
        except Exception as e:  # noqa: BLE001 - no browser, or the page would not load: the HTML path still runs
            logger.info("Feed capture failed for %s: %s", url, e)
            return None
        feed = recognise(responses, visible_text(html))
        if feed is None:
            say("no data feed behind this page's table; reading the page")
            return None
    say(f"found the page's data feed ({urlsplit(feed.url).netloc}{urlsplit(feed.url).path}"
        + (f", {feed.total} records" if feed.total else "") + ")")
    records = collect(feed, referer=url, max_rows=max_rows or _env_int("FEED_MAX_ROWS", 1000), period=period, on_fail=on_fail, log=say)
    if not records:
        return None
    mapping = column_mapping(records, columns, labels, goal)
    return to_rows(records, mapping)
