"""
Downloadable data files (CSV, TSV, XLSX, JSON) as a source.

Many publishers offer the records as a file rather than a table on the page (open-data portals, research repositories,
GitHub). Such a page used to be rejected for "not listing the records". Now its file links are found, each file is
downloaded to a temporary file (size-capped, plain request through the SSRF guard), read, mapped to the table's columns,
and the temporary file is deleted once its rows are stored (UniversalScrapeService._store_rows calls `release`). Old
leftovers (a crash between download and store) are swept on every download.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from typing import Any
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

logger = logging.getLogger(__name__)

EXTENSIONS = (".csv", ".tsv", ".xlsx", ".json")
TEMP_DIR = os.path.join(tempfile.gettempdir(), "awdax-datasets")
_HREF = re.compile(r"""<a\b[^>]*\bhref\s*=\s*["']([^"'#]+)["'][^>]*>(.*?)</a>""", re.I | re.S)
_lock = threading.Lock()
_held: dict[str, list[str]] = {}  # owner key -> temporary files waiting for their rows to be stored


def _ext(url: str) -> str:
    path = urlsplit(url).path.lower()
    return next((e for e in EXTENSIONS if path.endswith(e)), "")


def is_dataset_url(url: str) -> bool:
    return bool(_ext(url))


def direct_file_url(url: str) -> str:
    """GitHub shows a file inside a page (/blob/); the file itself is on raw.githubusercontent.com."""
    m = re.match(r"^https://github\.com/([^/]+)/([^/]+)/blob/(.+)$", url)
    return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else url


def find_dataset_links(html: str, base_url: str, *, limit: int = 10) -> list[str]:
    """Links on a page to data files it offers for download, in page order, addresses made absolute."""
    out: list[str] = []
    found = [urljoin(base_url, href.strip()) for href, _text in _HREF.findall(html or "")]
    # Pages that build their file list in JavaScript still carry the addresses in their source (JSON, data attributes).
    # Only table-file types here: a page's scripts are full of .json addresses that are app plumbing, not data.
    found += re.findall(r"""https://[^\s"'<>()\\]+?\.(?:csv|tsv|xlsx)(?:\?[^\s"'<>()\\]*)?(?=["'\s<)])""", html or "", re.I)
    for raw in found:
        url = direct_file_url(raw)
        if url.startswith("https://") and is_dataset_url(url) and url not in out:
            out.append(url)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- temporary files


def _sweep(max_age_s: float = 3600) -> None:
    """Remove leftovers older than `max_age_s` (a run that crashed between download and store)."""
    try:
        for name in os.listdir(TEMP_DIR):
            path = os.path.join(TEMP_DIR, name)
            if time.time() - os.path.getmtime(path) > max_age_s:
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
    except OSError:
        pass


def hold(owner: str, path: str) -> None:
    with _lock:
        _held.setdefault(owner, []).append(path)


def release(owner: str) -> int:
    """Delete the temporary files of `owner` (their rows are stored). Returns how many were deleted."""
    with _lock:
        paths = _held.pop(owner, [])
    deleted = 0
    for p in paths:
        try:
            os.remove(p)
            deleted += 1
        except FileNotFoundError:
            deleted += 1
        except OSError as e:
            logger.warning("Could not delete temporary dataset %s: %s", p, e)
    return deleted


class Refused(RuntimeError):
    """The host turned the plain request away (401/403/429): a browser may still be served."""


def download(url: str, *, max_mb: float | None = None) -> str:
    """The file at `url` saved in TEMP_DIR (plain request, SSRF guard, size cap). Raises RuntimeError when refused,
    too big, or when the address answers a web page instead of a file."""
    from discovery import _request_headers
    from url_guard import safe_get

    os.makedirs(TEMP_DIR, exist_ok=True)
    _sweep()
    cap = int((max_mb or float(os.getenv("DATASET_MAX_MB", "50"))) * 1024 * 1024)
    res = safe_get(url, timeout=60, headers=_request_headers(), max_bytes=cap + 1)
    if res.status_code in (401, 403, 429):
        raise Refused(f"HTTP {res.status_code}")
    if res.status_code != 200:
        raise RuntimeError(f"HTTP {res.status_code}")
    body = res.content or b""
    if len(body) > cap:
        raise RuntimeError(f"larger than {cap // (1024 * 1024)} MB")
    if body[:200].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise RuntimeError("the address answered a web page, not a data file")
    fd, path = tempfile.mkstemp(prefix="ds-", suffix=_ext(url) or ".bin", dir=TEMP_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(body)
    return path


# --------------------------------------------------------------------------- readers


def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _table_records(rows: list[list[str]]) -> list[dict[str, str]]:
    """Header row (the first with 2+ filled cells) + the rows under it, as records."""
    rows = [[str(c or "").strip() for c in r] for r in rows]
    start = next((i for i, r in enumerate(rows) if sum(1 for c in r if c) >= 2), None)
    if start is None:
        return []
    header = [h or f"column_{i + 1}" for i, h in enumerate(rows[start])]
    out = []
    for r in rows[start + 1:]:
        if any(r):
            out.append({header[i]: r[i] if i < len(r) else "" for i in range(len(header))})
    return out


def read_csv(data: bytes, *, delimiter: str | None = None) -> list[dict[str, str]]:
    text = _text(data)
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    return _table_records(list(csv.reader(io.StringIO(text), delimiter=delimiter)))


def read_json(data: bytes) -> list[dict[str, Any]]:
    from data_feed import find_records

    return find_records(json.loads(_text(data)))[1]


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(data: bytes) -> list[dict[str, str]]:
    """The first worksheet of an .xlsx, read with the standard library (an .xlsx is a zip of XML parts)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        sheet = "xl/worksheets/sheet1.xml"
        try:  # the workbook's first sheet, wherever it is stored
            first = ElementTree.fromstring(z.read("xl/workbook.xml")).find("m:sheets/m:sheet", _NS)
            rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            target = next(r.get("Target") for r in rels if r.get("Id") == first.get(_REL))
            sheet = "xl/" + target.lstrip("/").removeprefix("xl/")
        except (KeyError, StopIteration, AttributeError):
            pass
        rows: list[list[str]] = []
        for row in ElementTree.fromstring(z.read(sheet)).iter(f"{{{_NS['m']}}}row"):
            cells: dict[int, str] = {}
            for c in row.findall("m:c", _NS):
                kind, v = c.get("t"), c.find("m:v", _NS)
                if kind == "s" and v is not None:
                    value = shared[int(v.text)]
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
                else:
                    value = v.text if v is not None and v.text is not None else ""
                cells[_col_index(c.get("r") or "A")] = value
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        return _table_records(rows)


def read_file(path: str, url: str = "") -> list[dict[str, Any]]:
    with open(path, "rb") as f:
        data = f.read()
    ext = _ext(url) or os.path.splitext(path)[1].lower()
    if ext == ".xlsx" or data[:2] == b"PK":
        return read_xlsx(data)
    if ext == ".json" or data.lstrip()[:1] in (b"{", b"["):
        return read_json(data)
    return read_csv(data, delimiter="\t" if ext == ".tsv" else None)


def browser_download(url: str, *, timeout_s: float = 90.0) -> str:
    """Download `url` with headless Chrome into TEMP_DIR: for hosts that refuse a plain request (bot checks) but serve a
    browser. Raises RuntimeError when nothing arrives in time or the file is too big."""

    from url_guard import check_url

    check_url(url)
    os.makedirs(TEMP_DIR, exist_ok=True)
    folder = tempfile.mkdtemp(prefix="dl-", dir=TEMP_DIR)
    # No component updates: Chrome otherwise drops its own downloads (models, lists) into the same folder.
    opts = {"extra_args": ("--disable-component-update", "--no-first-run"), "window": None,
            "prefs": {"download.default_directory": folder, "download.prompt_for_download": False}}
    expected = os.path.basename(urlsplit(url).path).lower()
    ext = _ext(url)
    try:
        return _fetch_into(url, folder, opts, expected, ext, timeout_s)
    finally:
        shutil.rmtree(folder, ignore_errors=True)  # whatever else Chrome left there goes too


def _fetch_into(url: str, folder: str, opts: dict[str, Any], expected: str, ext: str, timeout_s: float) -> str:
    import browser

    driver = browser.launch(**opts)
    try:
        driver.execute_cdp_cmd("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": folder})
        try:
            driver.get(url)
        except Exception:  # noqa: BLE001 - a download often "fails" the page load; the file still arrives
            pass
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            # Only the file asked for: its name, or failing that its type (a server may rename it).
            names = [n for n in os.listdir(folder) if not n.endswith((".crdownload", ".tmp"))]
            done = [n for n in names if n.lower() == expected] or [n for n in names if ext and n.lower().endswith(ext)]
            if done:
                break
            time.sleep(1)
        else:
            raise RuntimeError("the browser did not download a file")
    finally:
        driver.quit()
    src = os.path.join(folder, done[0])
    cap = int(float(os.getenv("DATASET_MAX_MB", "50")) * 1024 * 1024)
    if os.path.getsize(src) > cap:
        os.remove(src)
        raise RuntimeError(f"larger than {cap // (1024 * 1024)} MB")
    fd, path = tempfile.mkstemp(prefix="ds-", suffix=_ext(url) or os.path.splitext(src)[1], dir=TEMP_DIR)
    os.close(fd)
    os.replace(src, path)
    return path


def records_from(url: str, *, owner: str, on_refused: Any = None) -> list[dict[str, Any]]:
    """Download `url` to a temporary file and read its records. The file stays until `release(owner)` (rows stored).
    A plain request comes first; when the host refuses it, `on_refused(reason)` is called (the failed-links record) and
    the file is fetched with the browser instead."""
    try:
        path = download(url)
    except Refused as e:
        if on_refused:
            on_refused(str(e))
        path = browser_download(url)
    hold(owner, path)
    return read_file(path, url)
