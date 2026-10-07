"""
The Google Maps run: turn a "places" intent into a table of businesses, with no scraping.

Where it searches:
  * Named places (one or several): each is geocoded and its area is cut into a grid of tiles (large regions such as
    "Delhi NCR" get many tiles, a locality gets one). Every tile is searched with every category, spread across tiles
    and categories so a small call budget still covers the whole region instead of one corner.
  * No place named ("near me"): rings around the user's position that widen (2, 5, 10, 20, 50 km) only while the
    target has not been reached.
Every search is paged (20 places a page, at most 60 a query), breadth first. All Google calls are metered
(places_search.charge); a run stops at its target, its own call budget, or the user's/monthly cap, and says which.
Worker threads only fetch; every database write and progress callback happens on the run's own thread.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, Callable
from urllib.parse import quote_plus

import places_search
import places_sites
from places_search import PlacesError, PlacesQuotaExceeded
from places_strategy import EXTRA_COLUMNS, places_table_schema
from reasoning import ScrapeIntent

logger = logging.getLogger(__name__)

Rect = tuple[float, float, float, float]  # low_lat, low_lng, high_lat, high_lng
RING_KM = (2, 5, 10, 20, 50)
MIN_AREA_KM = 3.0  # a geocoded point or tiny viewport is widened to this, so the search rectangle has an area
FOLLOW_UP_MIN_NEW = 5  # fetch a query's next page only while the page just read still brought new places
_WEB_SELLER = re.compile(r"\b(web|website|seo|digital|app|software|online|e-?commerce)\b", re.I)
_STATUS = {"OPERATIONAL": "Operational", "CLOSED_TEMPORARILY": "Temporarily closed"}


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


# ── geometry (pure) ─────────────────────────────────────────────────────────────────────────────────────────────

def bbox(lat: float, lng: float, radius_km: float) -> Rect:
    dlat = radius_km / 111.0
    dlng = radius_km / (111.32 * max(0.05, math.cos(math.radians(lat))))
    return (max(-90.0, lat - dlat), max(-180.0, lng - dlng), min(90.0, lat + dlat), min(180.0, lng + dlng))


def _size_km(rect: Rect) -> tuple[float, float]:
    mid = (rect[0] + rect[2]) / 2
    return (rect[2] - rect[0]) * 111.0, (rect[3] - rect[1]) * 111.32 * max(0.05, math.cos(math.radians(mid)))


def at_least(rect: Rect, min_km: float = MIN_AREA_KM) -> Rect:
    height, width = _size_km(rect)
    if height >= min_km and width >= min_km:
        return rect
    return bbox((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2, min_km / 2)


def grid_cells(viewport: Rect, tile_km: float, max_tiles: int) -> list[Rect]:
    """The viewport cut into tiles of about `tile_km` (larger if that would need more than `max_tiles`), nearest the
    centre first. The tiles always cover the whole viewport."""
    height_km, width_km = _size_km(viewport)
    size = max(tile_km, 0.5)
    while True:
        rows, cols = max(1, math.ceil(height_km / size)), max(1, math.ceil(width_km / size))
        if rows * cols <= max_tiles:
            break
        size *= 1.25
    lat_step = (viewport[2] - viewport[0]) / rows
    lng_step = (viewport[3] - viewport[1]) / cols
    cells = [
        (viewport[0] + r * lat_step, viewport[1] + c * lng_step, viewport[0] + (r + 1) * lat_step, viewport[1] + (c + 1) * lng_step)
        for r in range(rows)
        for c in range(cols)
    ]
    mid_r, mid_c = (rows - 1) / 2, (cols - 1) / 2
    order = sorted(range(len(cells)), key=lambda i: ((i // cols - mid_r) ** 2 + (i % cols - mid_c) ** 2, i))
    return [cells[i] for i in order]


def task_order(n_areas: int, n_terms: int) -> list[tuple[int, int]]:
    """Every (area, term) pair once, ordered so that whatever budget the run ends up with, the searches done so far have
    covered every area and as many different categories as possible: area `a` is searched with category `(a + shift) % T`
    for shift 0, 1, 2 ...  (a Latin square: no area repeats a category and no category repeats in a row until it must)."""
    return [(a, (a + shift) % n_terms) for shift in range(n_terms) for a in range(n_areas)]


def maps_search_url(term: str, place: str) -> str:
    where = "near me" if place.startswith(("within", "near")) else f"in {place}"
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(f'{term} {where}'.strip())}"


# ── places → rows ───────────────────────────────────────────────────────────────────────────────────────────────

def _text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("text")
    return " ".join(str(value or "").split())


def _yes_no(value: Any) -> str:
    return "" if value is None else ("yes" if value else "no")


def lead_score(row: dict[str, str], lead_focus: str) -> int:
    """0-100. Reachable (phone), well rated, well reviewed, open for business, plus the website signal: someone who sells
    web services wants businesses with NO website; for any other lead focus, a business that has one is easier to reach."""
    score = 0
    if row.get("phone"):
        score += 25
    try:
        if float(row.get("rating") or 0) >= 4.0:
            score += 20
        if int(float(row.get("reviews") or 0)) >= 50:
            score += 15
    except ValueError:
        pass
    if row.get("business_status") == "Operational":
        score += 10
    # A listed website that no longer exists counts as no website: it is not a way to reach them and not a site to keep.
    has_site = row.get("has_website") == "yes" and not places_sites.is_dead_site(row)
    sells_web = bool(lead_focus and _WEB_SELLER.search(lead_focus))
    if has_site != sells_web:  # sells web: wants no site; otherwise: wants one
        score += 30
    # Once the website has been read: a site with things to fix is a prospect for a web seller, and an email is a way in.
    if sells_web and has_site and places_sites.is_weak_site(row):
        score += 20
    if row.get("email"):
        score += 5
    return min(score, 100)


def place_row(place: dict[str, Any], *, term: str, area: str, extra_fields: list[str], lead_focus: str) -> dict[str, str] | None:
    """One Google place as the row of the table, or None when it is not a usable lead (no name, permanently closed)."""
    pid = str(place.get("id") or "").strip()
    name = _text(place.get("displayName"))
    if not pid or not name or place.get("businessStatus") == "CLOSED_PERMANENTLY":
        return None
    website = str(place.get("websiteUri") or "").strip()
    rating = place.get("rating")
    reviews = place.get("userRatingCount")
    row = {
        "id": pid,
        "name": name,
        "category": _text(place.get("primaryTypeDisplayName")) or str(place.get("primaryType") or "").replace("_", " ").capitalize(),
        "phone": str(place.get("nationalPhoneNumber") or "").strip(),
        "website": website,
        "has_website": "yes" if website else "no",
        "rating": f"{float(rating):g}" if isinstance(rating, (int, float)) else "",
        "reviews": str(int(reviews)) if isinstance(reviews, (int, float)) else "",
        "address": _text(place.get("formattedAddress")),
        "area": area,
        "source_url": str(place.get("googleMapsUri") or "").strip() or maps_search_url(name, area),
        "business_status": _STATUS.get(str(place.get("businessStatus") or ""), str(place.get("businessStatus") or "").replace("_", " ").title()),
        "matched_query": term,
    }
    for extra in extra_fields:
        col = EXTRA_COLUMNS[extra][0]
        if extra == "opening_hours":
            row[col] = " | ".join((place.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [])
        elif extra == "price_level":
            row[col] = str(place.get("priceLevel") or "").replace("PRICE_LEVEL_", "").replace("_", " ").title()
        else:
            row[col] = _yes_no(place.get({"delivery": "delivery", "dine_in": "dineIn", "takeout": "takeout", "vegetarian": "servesVegetarianFood"}[extra]))
    row["lead_score"] = str(lead_score(row, lead_focus))
    return row


# ── where to search ─────────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Area:
    label: str  # shown in the table and on the source card: the place the user named, or "within 5 km"
    rect: Rect | None = None  # None: search by name, with the place in the query text
    in_text: str = ""  # appended to the query when there is no rectangle


@dataclass(frozen=True)
class Task:
    area: int
    term: int
    token: str | None = None


def area_groups(cfg: dict[str, Any], location_hint: dict[str, Any] | None) -> list[list[Area]]:
    """Groups searched in order; the next group is only used while the target is not yet reached."""
    locations = [str(x) for x in cfg.get("locations") or []]
    if locations:
        tile_km = _env_float("PLACES_TILE_KM", 8.0)
        max_tiles = _env_int("PLACES_MAX_TILES_PER_LOCATION", 16)
        per_location: list[list[Area]] = []
        for name in locations:
            geo = places_search.geocode(name)
            if geo:
                cells = grid_cells(at_least(tuple(geo["viewport"])), tile_km, max_tiles)  # type: ignore[arg-type]
                per_location.append([Area(name, cell) for cell in cells])
            else:
                per_location.append([Area(name, None, f" in {name}")])
        # Alternate between the places so a short budget still reaches each of them.
        merged = [a for group in zip_longest(*per_location) for a in group if a is not None]
        return [merged]
    center = _center(location_hint)
    if center is None:
        raise PlacesError("Name a city or area in your request (for example “cafes in Pune”), or allow location access so “near me” works.")
    return [[Area(f"within {km} km", bbox(center[0], center[1], km))] for km in RING_KM]


def _center(hint: dict[str, Any] | None) -> tuple[float, float] | None:
    try:
        if hint and hint.get("lat") is not None and hint.get("lng") is not None:
            return float(hint["lat"]), float(hint["lng"])
    except (TypeError, ValueError):
        pass
    raw = (os.getenv("PLACES_DEFAULT_CENTER") or "").strip()
    if raw:
        try:
            lat, lng = (float(p) for p in raw.split(","))
            return lat, lng
        except ValueError:
            logger.warning("PLACES_DEFAULT_CENTER must look like 28.61,77.21")
    return None


def _read_websites(
    rows: dict[str, dict[str, str]],
    lead_focus: str,
    cfg: dict[str, Any],
    progress: Callable[[str, str], None],
    flush: Callable[[], None],
    check_alive: Callable[[], None] | None,
) -> dict[str, int]:
    """Open the businesses' own websites (best leads first) and fill in what they say: email, social links, site problems.

    The table is saved after every batch, so it fills in while this runs. Scores are worked out again once a row has
    its website facts."""
    ordered = sorted(rows.values(), key=lambda r: -int(r["lead_score"]))
    with_site = sum(1 for r in ordered if r.get("website"))
    progress("extracting", f"Reading {with_site} business websites for contact details…")

    def after_batch(done: int, total: int) -> None:
        for row in ordered:
            row["lead_score"] = str(lead_score(row, lead_focus))
        progress("extracting", f"Read {done} of {total} business websites")
        flush()

    stats = places_sites.enrich(
        ordered,
        workers=_env_int("PLACES_SITE_WORKERS", 8),
        max_sites=_env_int("PLACES_SITE_MAX", 150),
        time_budget_s=_env_float("PLACES_SITE_TIME_BUDGET_S", 150.0),
        timeout=_env_float("PLACES_SITE_TIMEOUT_S", 10.0),
        on_batch=after_batch,
        check_alive=check_alive,
    )
    for row in ordered:  # rows with no website never get a batch
        row["lead_score"] = str(lead_score(row, lead_focus))
    flush()
    return stats


# ── the run ─────────────────────────────────────────────────────────────────────────────────────────────────────

def run_places_job(
    sess: dict[str, Any],
    intent: ScrapeIntent,
    *,
    user_id: str,
    location_hint: dict[str, Any] | None = None,
    on_progress: Callable[[str, str], None] | None = None,
    on_source: Callable[[dict[str, Any]], None] | None = None,
    check_alive: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Search, store and announce the places for `intent`. Returns {"places", "areas", "calls", "stopped", ...}.

    `check_alive` raises when the chat was deleted, so a deleted chat stops spending Google calls."""
    from scraper import universal_service

    cfg = intent.places or {}
    terms = [str(t) for t in cfg.get("search_terms") or []] or [intent.topic]
    extra_fields = [e for e in cfg.get("extra_fields") or [] if e in EXTRA_COLUMNS]
    lead_focus = str(cfg.get("lead_focus") or "")
    target = int(cfg.get("target_count") or 60)
    schema = sess.get("table_schema") or places_table_schema(intent)
    columns: list[str] = list(schema["columns"])
    labels: list[str] = list(schema.get("column_labels") or columns)
    mask = places_search.field_mask_for(extra_fields)
    max_calls = _env_int("PLACES_MAX_CALLS_PER_RUN", 40)
    workers = _env_int("PLACES_WORKERS", 4)
    job_id = intent.job_id

    def progress(phase: str, message: str) -> None:
        if on_progress:
            on_progress(phase, message)

    progress("discovery", "Finding the areas to search on Google Maps…")
    groups = area_groups(cfg, location_hint)
    places_search.register_job(job_id)
    n_areas = sum(len(g) for g in groups)

    rows: dict[str, dict[str, str]] = {}  # place id -> row
    per_source: dict[tuple[str, str], int] = {}  # (term, place named) -> places it found
    per_term: dict[str, int] = {}  # category -> new places it found
    # One category may bring at most 1.5x its even share of the target while others are still waiting, so the target can't be
    # filled by the first two categories alone (the cap lifts if nothing else is left to search).
    term_cap = math.ceil(target / max(1, len(terms)) * 1.5)
    errors: list[PlacesError] = []
    searched: set[tuple[str, str]] = set()
    calls = 0
    stopped = "exhausted"

    def flush() -> None:
        ordered = sorted(rows.values(), key=lambda r: (-int(r["lead_score"]), -int(r["reviews"] or 0), r["name"].lower()))
        table_rows = [{c: r.get(c, "") for c in columns} for r in ordered]
        universal_service.save_merged_table(job_id, {"columns": columns, "column_labels": labels, "rows": table_rows, "row_count": len(table_rows)})
        universal_service.emit_event("table", {"job_id": job_id})

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="places") as pool:
        for gi, group in enumerate(groups):
            if len(groups) > 1 and gi > 0:
                progress("discovery", f"Only {len(rows)} of {target} places so far; widening the search to {group[0].label}")
            tasks = deque(Task(a, t) for a, t in task_order(len(group), len(terms)))
            deferred: list[Task] = []  # searches of a category that has already had its share of the target
            cap_on = len(terms) > 1
            while tasks or deferred:
                if len(rows) >= target:
                    stopped = "target"
                    break
                if calls >= max_calls:
                    stopped = "budget"
                    break
                if not tasks:  # only categories that already had their share are left and the target is not reached: lift the cap
                    tasks.extend(deferred)
                    deferred.clear()
                    cap_on = False
                if check_alive:
                    check_alive()
                batch = []
                while tasks and len(batch) < min(workers, max_calls - calls):
                    task = tasks.popleft()
                    if cap_on and per_term.get(terms[task.term], 0) >= term_cap:
                        deferred.append(task)
                        continue
                    batch.append(task)
                if not batch:
                    continue
                try:
                    places_search.charge(user_id, len(batch))
                except PlacesQuotaExceeded as exc:
                    stopped = "quota"
                    errors.append(exc)
                    tasks.clear()
                    deferred.clear()
                    break
                calls += len(batch)

                def fetch(task: Task, group: list[Area] = group) -> Any:
                    area = group[task.area]
                    try:
                        return places_search.search_text(terms[task.term] + area.in_text, field_mask=mask, rect=area.rect, page_token=task.token)
                    except PlacesError as exc:
                        return exc
                    except Exception as exc:  # a malformed answer must cost this search only, not the whole run
                        logger.warning("Places search failed: %s", exc)
                        return PlacesError("Google Maps sent an answer that could not be read.")

                results = list(pool.map(fetch, batch))
                failed = 0
                for task, result in zip(batch, results):
                    area, term = group[task.area], terms[task.term]
                    if isinstance(result, PlacesError):
                        failed += 1
                        errors.append(result)
                        continue
                    found, token = result
                    new = 0
                    for place in found:
                        row = place_row(place, term=term, area=area.label, extra_fields=extra_fields, lead_focus=lead_focus)
                        if row is None or row["id"] in rows:
                            continue
                        rows[row["id"]] = row
                        new += 1
                        universal_service.store_record(job_id, row["source_url"], dict(row))
                    key = (term, area.label)
                    per_source[key] = per_source.get(key, 0) + new
                    per_term[term] = per_term.get(term, 0) + new
                    searched.add(key)
                    if on_source:
                        on_source({
                            "url": maps_search_url(term, area.label),
                            "title": f"Google Maps: {term} — {area.label}",
                            "status": "validated",
                            "domain": "google.com",
                            "origin": "places",
                            "reason": f"{per_source[key]} places",
                        })
                    if token and new >= FOLLOW_UP_MIN_NEW:
                        tasks.append(Task(task.area, task.term, token))
                last = group[batch[-1].area].label
                progress("extracting", f"Searched “{terms[batch[-1].term]}” in {last}: {len(rows)} places so far ({calls} Google requests)")
                if rows:
                    flush()
                if failed == len(batch) and not rows:
                    raise errors[-1]
            else:
                continue
            break  # the inner loop stopped on a limit, not because it ran out of tasks
    if stopped == "exhausted" and len(rows) >= target:
        stopped = "target"
    if not rows:
        if errors:
            raise errors[-1]
        raise PlacesError("Google Maps found no places for this request. Try a broader search or another area.")
    flush()
    sites = _read_websites(rows, lead_focus, cfg, progress, flush, check_alive) if cfg.get("scrape_sites") else None
    if sites is not None:
        # The table is complete now: keep the stored rows in step with what was read.
        for row in rows.values():
            universal_service.store_record(job_id, row["source_url"], dict(row))
    return {
        "websites": sites,
        "places": len(rows),
        "areas": n_areas,
        "searched": len(searched),
        "calls": calls,
        "stopped": stopped,
        "target": target,
        "terms": terms,
        "locations": list(cfg.get("locations") or []) or ["near you"],
        "error": str(errors[-1]) if errors else "",
    }
