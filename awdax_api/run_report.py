from __future__ import annotations

from typing import Any


_STOPPED = {
    "target": "the number of places you asked for was reached",
    "budget": "the per-run Google request limit was reached (raise PLACES_MAX_CALLS_PER_RUN for more)",
    "quota": "the Google Maps request budget is used up",
    "exhausted": "Google Maps had no more places for these searches",
}


def _format_places_report(sess: dict[str, Any], stats: dict[str, Any], *, goal: str) -> str:
    lines = [
        "=== AWDAX GOOGLE MAPS SEARCH ===",
        f"Goal: {goal}",
        "Status: complete",
        "",
        f"Found {stats.get('places', 0)} places in {', '.join(stats.get('locations') or [])} "
        f"({stats.get('calls', 0)} Google requests, {stats.get('searched', 0)} searches over {stats.get('areas', 0)} areas)",
        "Searched for: " + ", ".join(stats.get("terms") or []),
        "Stopped because: " + _STOPPED.get(str(stats.get("stopped")), str(stats.get("stopped") or "")),
    ]
    sites = stats.get("websites")
    if sites:
        lines.append(f"Websites: {sites.get('read', 0)} read of {sites.get('sites', 0)} ({sites.get('emails', 0)} with an email, {sites.get('failed', 0)} could not be read, {sites.get('skipped', 0)} skipped)")
    if stats.get("error"):
        lines.append(f"Note: {stats['error']}")
    cols = (sess.get("table_schema") or {}).get("columns") or []
    if cols:
        lines += ["", "Columns: " + ", ".join(str(c) for c in cols)]
    return "\n".join(lines)


def _failed_links(sess: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from url_access import failures_for_job

        return failures_for_job(str(sess.get("job_id") or ""))
    except Exception:  # the report must never fail because a side table could not be read
        return []


def format_discovery_report(sess: dict[str, Any], *, goal: str) -> str:
    if sess.get("places_stats"):
        return _format_places_report(sess, sess["places_stats"], goal=goal)
    sources = sess.get("sources") or []
    plans = sess.get("plans") or []
    queries = sess.get("search_queries") or []
    lines = [
        "=== AWDAX SOURCE DISCOVERY ===",
        f"Goal: {goal}",
        "Status: complete",
        "",
    ]
    research = sess.get("research") or {}
    sites = research.get("websites") or []
    if sites:
        lines.append(f"WEB RESEARCH: top {len(sites)} websites, tried in this order")
        if research.get("understanding"):
            lines.append(f"Understood as: {research['understanding']}")
        for s in sites:
            lines.append(f"{s.get('rank')}. {s.get('site_name') or s.get('domain')}: {s.get('url')}")
            if s.get("what_it_has"):
                lines.append(f"   Has: {s['what_it_has']}")
        if research.get("searched"):
            lines.append("Searched Google for: " + "; ".join(research["searched"][:6]))
        lines.append("")
    lines.append(f"Discovery strategies ({len(queries)} searches)")
    for q in queries[:12]:
        text = q.get("query") if isinstance(q, dict) else str(q)
        if text:
            lines.append(f"- {text}")
    lines.append("")
    lines.append(f"VALIDATED SOURCES ({len(plans)})")
    for i, plan in enumerate(plans[:20], start=1):
        p = plan if isinstance(plan, dict) else {}
        name = p.get("source_name") or "Source"
        url = p.get("source_url") or p.get("entry_url") or ""
        dry = p.get("dry_run_rows")
        conf = p.get("confidence")
        lines.append(f"{i}. {name}")
        lines.append(f"   URL: {url}")
        if dry is not None:
            lines.append(f"   Dry-run rows: {dry}")
        if conf is not None:
            lines.append(f"   Confidence: {conf}")
    blocked = [p for p in plans if isinstance(p, dict) and p.get("blocked")]
    lines.append("")
    lines.append(f"REJECTED ({len(blocked)})")
    for p in blocked[:10]:
        url = p.get("source_url") or p.get("entry_url") or ""
        lines.append(f"- {p.get('source_name') or url}: blocked or failed inspect")
    if not sources and not plans:
        lines.append("(No external sources — official preset or empty discovery.)")
    failed = _failed_links(sess)
    if failed:
        lines.append("")
        lines.append(f"LINKS THAT FAILED THEIR PLAIN REQUEST ({len(failed)}): see Sources → Failed links")
        for f in failed[:8]:
            lines.append(f"- {f['url']}: {f['outcome']} ({f['reason']})")
    lines.append("")
    schema = sess.get("table_schema") or {}
    cols = schema.get("columns") or []
    if cols:
        lines.append("Expected columns: " + ", ".join(str(c) for c in cols))
    return "\n".join(lines)
