from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from reasoning import ScrapeIntent
from regulatory_strategy import intent_uses_regulatory_feed
from scraper import universal_service


def _cell_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _record_stub(row_id: str, source_url: str = "") -> dict[str, Any]:
    return {
        "id": row_id,
        "tier": "unscored",
        "status": "accepted",
        "score": None,
        "source_url": source_url,
        "source_domain": urlparse(source_url).netloc if source_url else "",
    }


def dataset_row_count(sess: dict[str, Any]) -> int:
    table = build_dataset_table(sess, limit=5000)
    if table and table.get("rows"):
        return len(table["rows"])
    return 0


def build_dataset_table(sess: dict[str, Any], *, limit: int = 5000, include_partial: bool = False) -> dict[str, Any] | None:
    _ = include_partial
    intent_data = sess.get("intent")
    job_id = sess.get("job_id")
    if intent_data and intent_uses_regulatory_feed(ScrapeIntent.from_dict(intent_data)):
        return _regulatory_dataset(sess, limit=limit)
    if job_id and intent_data and intent_data.get("pipeline") == "places":
        # Already ranked and complete as the run saved it: never re-merged (that would fold branches of one business
        # into one row and ask the model to rewrite them).
        merged = universal_service.get_merged_table(job_id)
        return _merged_to_dataset(merged, job_id=job_id) if merged else None
    if job_id:
        merged = universal_service.get_merged_table(job_id)
        if not merged:
            raw = universal_service.list_raw_records(job_id, limit=limit)
            if raw and intent_data:
                from table_merge import merge_records

                merged = merge_records(ScrapeIntent.from_dict(intent_data), raw)
                if merged.get("rows"):
                    universal_service.save_merged_table(job_id, merged)
        if merged and merged.get("rows"):
            return _merged_to_dataset(merged, job_id=job_id)
    return None


def _merged_to_dataset(merged: dict[str, Any], *, job_id: str) -> dict[str, Any]:
    columns = list(merged.get("columns") or [])
    labels = merged.get("column_labels") or columns
    if "source_url" not in columns:
        columns = columns + ["source_url"]
    rows_out: list[list[str]] = []
    records: list[dict[str, Any]] = []
    for i, row in enumerate(merged.get("rows") or []):
        if isinstance(row, dict):
            src = _cell_str(row.get("source_url") or row.get("source") or "")
            cells = [_cell_str(row.get(c) if c != "source_url" else (row.get("source_url") or row.get("source") or src)) for c in columns]
        else:
            seq = list(row) if isinstance(row, (list, tuple)) else []
            cells = [_cell_str(c) for c in seq]
            while len(cells) < len(columns):
                cells.append("")
            src = cells[columns.index("source_url")] if "source_url" in columns else ""
        rows_out.append(cells)
        ext = _cell_str(row.get("external_id") if isinstance(row, dict) else (cells[0] if cells else i))
        records.append(_record_stub(f"{job_id}:{ext or i}", src))
    topic = labels[0] if labels else "dataset"
    labels = [str(x) for x in labels]
    return {
        "name": str(topic),
        "source_url": "",
        "columns": columns,
        # Readable headers, aligned with `columns` (the appended source_url keeps its own name).
        "column_labels": labels[: len(columns)] + [c.replace("_", " ").capitalize() for c in columns[len(labels) :]],
        "rows": rows_out,
        "row_count": len(rows_out),
        "records": records,
    }


def _regulatory_dataset(sess: dict[str, Any], *, limit: int) -> dict[str, Any] | None:
    from RegulatoryFeed import feed_service

    items = feed_service.list_feed(limit=limit)
    snap = set(sess.get("regulatory_feed_snapshot_ids") or [])
    if snap:
        items = [it for it in items if it.get("id") in snap or it.get("gazette_id") in snap]
    if not items and snap:
        return None
    if not items:
        items = feed_service.list_feed(limit=min(limit, 200))
    columns = [
        "gazette_id",
        "ministry",
        "subject",
        "issue_date",
        "publish_date",
        "topic",
        "summary",
        "importance",
        "pdf_url",
        "source_url",
    ]
    rows_out: list[list[str]] = []
    records: list[dict[str, Any]] = []
    for it in items:
        pdf = _cell_str(it.get("pdf_url"))
        rows_out.append(
            [
                _cell_str(it.get("gazette_id")),
                _cell_str(it.get("ministry")),
                _cell_str(it.get("subject")),
                _cell_str(it.get("issue_date")),
                _cell_str(it.get("publish_date")),
                _cell_str(it.get("topic")),
                _cell_str(it.get("summary")),
                _cell_str(it.get("importance") or "medium"),
                pdf,
                pdf or "https://egazette.gov.in",
            ]
        )
        gid = _cell_str(it.get("gazette_id")) or str(it.get("id"))
        records.append(_record_stub(gid, pdf or "https://egazette.gov.in"))
    if not rows_out:
        return None
    return {
        "name": "eGazette notifications",
        "source_url": "https://egazette.gov.in",
        "columns": columns,
        "rows": rows_out,
        "row_count": len(rows_out),
        "records": records,
    }


def build_dashboard(sess: dict[str, Any]) -> dict[str, Any]:
    table = build_dataset_table(sess, limit=5000)
    rows_total = table["row_count"] if table else 0
    goal = sess.get("goal") or ""
    return {
        "instance": {
            "id": sess["id"],
            "title": sess.get("title") or "Untitled chat",
            "goal": goal,
            "archived": bool(sess.get("archived")),
            "live_enabled": bool(sess.get("keep_live")),
            "created_at": sess["created_at"],
            "updated_at": sess["updated_at"],
            "dataset_row_count": rows_total,
        },
        "rows_total": rows_total,
        "table": table,
    }
