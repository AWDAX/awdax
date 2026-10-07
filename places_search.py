"""
Google Maps Platform client for the places pipeline: Places API (New) Text Search, Geocoding, and a usage meter.

This module is the only place that talks to Google, so another provider can be swapped in by replacing
`search_text` / `geocode` (PLACES_PROVIDER). Billing is per request, by the most expensive field asked for, so every
call goes through `charge()` first: a per-user daily cap and a monthly cap (default 1,000 calls, the Enterprise free
tier, so the default configuration costs nothing).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from places_strategy import maps_api_key

logger = logging.getLogger(__name__)

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
PAGE_SIZE = 20  # the API's maximum per page; a query returns at most 3 pages (60 places)
TIMEOUT_S = 20
RETRIES = 4  # attempts per Google request; after the fourth failure the search stops and says so (it never falls back to scraping)
GEO_TTL_DAYS = 30  # Google's terms let coordinates be cached for 30 days at most

# Core fields. Asking for a phone number, website or rating makes the call the Enterprise tier, so all contact
# fields come in one call rather than a cheaper search plus a per-place details call.
CORE_FIELDS = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.googleMapsUri",
    "places.primaryTypeDisplayName",
    "places.primaryType",  # the plain type ("coaching_center") for places Google has no display name for
    "places.businessStatus",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "nextPageToken",
)
# Opt-in extras (places_strategy.EXTRA_COLUMNS). delivery/dine-in/takeout/vegetarian are the pricier Atmosphere tier.
EXTRA_FIELD_MASKS = {
    "opening_hours": "places.regularOpeningHours",
    "price_level": "places.priceLevel",
    "delivery": "places.delivery",
    "dine_in": "places.dineIn",
    "takeout": "places.takeout",
    "vegetarian": "places.servesVegetarianFood",
}


class PlacesError(RuntimeError):
    """A Google call failed in a way retrying will not fix; the message is safe to show."""


class PlacesQuotaExceeded(PlacesError):
    """The daily or monthly call budget is used up."""


def field_mask_for(extra_fields: list[str] | None = None) -> str:
    fields = list(CORE_FIELDS)
    for extra in extra_fields or []:
        mask = EXTRA_FIELD_MASKS.get(extra)
        if mask and mask not in fields:
            fields.append(mask)
    return ",".join(fields)


# ── usage meter and geocode cache (same SQLite database as the rest of the app) ─────────────────────────────────

_db_lock = threading.Lock()


def _db():
    from RegulatoryFeed import _get_db

    return _get_db()


def _ensure_tables(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS places_usage (
            day TEXT NOT NULL,
            user_id TEXT NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, user_id)
        );
        CREATE TABLE IF NOT EXISTS places_jobs (
            job_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS geo_cache (
            query TEXT PRIMARY KEY,
            json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def charge(user_id: str, calls: int = 1) -> None:
    """Reserve `calls` Google requests for this user, or raise PlacesQuotaExceeded. Atomic across threads."""
    if calls <= 0:
        return
    today = datetime.now(timezone.utc)
    day = today.strftime("%Y-%m-%d")
    month = today.strftime("%Y-%m")
    per_user = _int_env("PLACES_MAX_CALLS_PER_USER_DAY", 200)
    monthly = _int_env("PLACES_MONTHLY_CALL_CAP", 1000)
    with _db_lock:
        conn = _db()
        try:
            _ensure_tables(conn)
            used_today = conn.execute("SELECT COALESCE(SUM(calls),0) FROM places_usage WHERE day=? AND user_id=?", (day, user_id)).fetchone()[0]
            used_month = conn.execute("SELECT COALESCE(SUM(calls),0) FROM places_usage WHERE day LIKE ?", (f"{month}-%",)).fetchone()[0]
            if used_today + calls > per_user:
                raise PlacesQuotaExceeded(f"Your daily Google Maps search limit ({per_user} requests) is used up. Try again tomorrow.")
            if used_month + calls > monthly:
                raise PlacesQuotaExceeded("This month's Google Maps search budget is used up, so no new places can be searched until next month.")
            conn.execute(
                """INSERT INTO places_usage (day, user_id, calls) VALUES (?,?,?)
                   ON CONFLICT(day, user_id) DO UPDATE SET calls = calls + excluded.calls""",
                (day, user_id, calls),
            )
            conn.commit()
        finally:
            conn.close()


def register_job(job_id: str) -> None:
    """Remember that this job holds Google Maps data, so PLACES_RETENTION_DAYS can delete it later."""
    with _db_lock:
        conn = _db()
        try:
            _ensure_tables(conn)
            conn.execute("INSERT OR IGNORE INTO places_jobs (job_id, created_at) VALUES (?,?)", (job_id, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        finally:
            conn.close()


def purge_expired(days: int | None = None) -> int:
    """Delete the stored rows of Maps jobs older than `days` (default PLACES_RETENTION_DAYS; 0 or unset keeps everything).

    Google's terms limit how long Places content may be stored; this is the owner's switch for it. The chats stay,
    with an empty table. Returns the number of jobs purged."""
    if days is None:
        try:
            days = int(os.getenv("PLACES_RETENTION_DAYS", "0") or 0)
        except ValueError:
            days = 0
    if days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    purged = 0
    with _db_lock:
        conn = _db()
        try:
            _ensure_tables(conn)
            for row in conn.execute("SELECT job_id FROM places_jobs WHERE created_at < ?", (cutoff,)).fetchall():
                job_id = row["job_id"]
                for table in ("records", "merged_tables"):
                    try:
                        conn.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))
                    except sqlite3.OperationalError:
                        pass  # the scrape tables do not exist yet: nothing to delete
                conn.execute("DELETE FROM places_jobs WHERE job_id=?", (job_id,))
                purged += 1
            conn.commit()
        finally:
            conn.close()
    if purged:
        logger.info("Deleted the stored Google Maps data of %d job(s) older than %d days", purged, days)
    return purged


def usage_this_month() -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with _db_lock:
        conn = _db()
        try:
            _ensure_tables(conn)
            return int(conn.execute("SELECT COALESCE(SUM(calls),0) FROM places_usage WHERE day LIKE ?", (f"{month}-%",)).fetchone()[0])
        finally:
            conn.close()


# ── Google calls ────────────────────────────────────────────────────────────────────────────────────────────────

def _post(body: dict[str, Any], field_mask: str) -> dict[str, Any]:
    key = maps_api_key()
    if not key:
        raise PlacesError("Google Maps is not set up on this server (GOOGLE_MAPS_API_KEY).")
    headers = {"Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": field_mask}
    last = "no answer"
    for attempt in range(RETRIES):
        try:
            res = requests.post(SEARCH_URL, json=body, headers=headers, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            last = type(exc).__name__
        else:
            if res.status_code == 200:
                return res.json() if res.content else {}
            last = f"HTTP {res.status_code}"
            if res.status_code not in (429, 500, 502, 503, 504):
                logger.warning("Places search refused (%s): %s", res.status_code, res.text[:300])
                raise PlacesError(_refusal(res.status_code, res.text))
        time.sleep(min(4.0, 0.5 * 2**attempt))
    raise PlacesError(f"Google Maps did not answer ({last}). Try again in a few minutes.")


def _refusal(status: int, text: str) -> str:
    if status in (400,):
        return "Google Maps rejected the search request."
    if status in (401, 403):
        detail = ""
        try:
            detail = str((json.loads(text).get("error") or {}).get("message") or "")
        except ValueError:
            pass
        return f"Google Maps refused the API key ({detail[:140] or 'check that Places API (New) is enabled and billing is on'})."
    return f"Google Maps returned an error (HTTP {status})."


def _latlng(lat: float, lng: float) -> dict[str, float]:
    return {"latitude": round(float(lat), 6), "longitude": round(float(lng), 6)}


def search_text(
    text_query: str,
    *,
    field_mask: str,
    rect: tuple[float, float, float, float] | None = None,
    circle: tuple[float, float, float] | None = None,
    page_token: str | None = None,
    region: str = "in",
    language: str = "en",
) -> tuple[list[dict[str, Any]], str | None]:
    """One Text Search page: (places, next_page_token).

    rect = (low_lat, low_lng, high_lat, high_lng) is a hard restriction; circle = (lat, lng, radius_m) only biases."""
    body: dict[str, Any] = {"textQuery": text_query, "pageSize": PAGE_SIZE, "regionCode": region, "languageCode": language}
    if rect:
        body["locationRestriction"] = {"rectangle": {"low": _latlng(rect[0], rect[1]), "high": _latlng(rect[2], rect[3])}}
    elif circle:
        body["locationBias"] = {"circle": {"center": _latlng(circle[0], circle[1]), "radius": float(min(max(circle[2], 1.0), 50000.0))}}
    if page_token:
        body["pageToken"] = page_token
    data = _post(body, field_mask)
    return list(data.get("places") or []), (data.get("nextPageToken") or None)


def _geo(value: Any) -> dict[str, Any] | None:
    """A cached geocode as the same tuples a fresh one returns (JSON turns tuples into lists)."""
    if not value:
        return None
    return {"center": tuple(value["center"]), "viewport": tuple(value["viewport"])}


def geocode(name: str, *, region: str = "in") -> dict[str, Any] | None:
    """A place name's centre and viewport: {"center": (lat, lng), "viewport": (sw_lat, sw_lng, ne_lat, ne_lng)}.

    Cached for 30 days. None when Google cannot place the name (or the Geocoding API is not enabled): the caller then
    searches by the name inside the query text instead."""
    query = " ".join((name or "").lower().split())
    if not query:
        return None
    with _db_lock:
        conn = _db()
        try:
            _ensure_tables(conn)
            row = conn.execute("SELECT json, created_at FROM geo_cache WHERE query=?", (query,)).fetchone()
            if row:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])
                if age.days < GEO_TTL_DAYS:
                    return _geo(json.loads(row["json"]))
                conn.execute("DELETE FROM geo_cache WHERE query=?", (query,))
                conn.commit()
        finally:
            conn.close()
    key = maps_api_key()
    if not key:
        return None
    try:
        res = requests.get(GEOCODE_URL, params={"address": name, "region": region, "key": key}, timeout=TIMEOUT_S)
        data = res.json() if res.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        return None
    results = data.get("results") or []
    found: dict[str, Any] | None = None
    if data.get("status") == "OK" and results:
        geo = results[0].get("geometry") or {}
        loc = geo.get("location") or {}
        view = geo.get("viewport") or geo.get("bounds") or {}
        try:
            center = (float(loc["lat"]), float(loc["lng"]))
            sw, ne = view.get("southwest") or loc, view.get("northeast") or loc
            found = {"center": center, "viewport": (float(sw["lat"]), float(sw["lng"]), float(ne["lat"]), float(ne["lng"]))}
        except (KeyError, TypeError, ValueError):
            found = None
    elif data.get("status") not in ("ZERO_RESULTS", "OK", None):
        logger.warning("Geocoding unavailable (%s); searching by name instead", data.get("status"))
        return None  # not cached: it may work once the API is enabled
    with _db_lock:
        conn = _db()
        try:
            _ensure_tables(conn)
            conn.execute(
                "INSERT OR REPLACE INTO geo_cache (query, json, created_at) VALUES (?,?,?)",
                (query, json.dumps(found), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    return found
