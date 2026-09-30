from __future__ import annotations

from typing import Any


def format_discovery_report(sess: dict[str, Any], *, goal: str) -> str:
    sources = sess.get("sources") or []
    plans = sess.get("plans") or []
    queries = sess.get("search_queries") or []
    lines = [
        "=== AWDAX SOURCE DISCOVERY ===",
        f"Goal: {goal}",
        "Status: complete",
        "",
        f"Discovery strategies ({len(queries)} searches)",
    ]
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
    lines.append("")
    schema = sess.get("table_schema") or {}
    cols = schema.get("columns") or []
    if cols:
        lines.append("Expected columns: " + ", ".join(str(c) for c in cols))
    return "\n".join(lines)
