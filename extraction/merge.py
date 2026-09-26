"""Merge per-source tables into one master dataset."""

from __future__ import annotations

from urllib.parse import urlparse

from extraction.models import ExtractedTable

_S_NO = "S. No."
_SOURCE_COLS = ("source", "source_url", _S_NO.lower(), "s_no")


def _source_label(table: ExtractedTable) -> str:
    host = urlparse(table.source_url).netloc.lower().removeprefix("www.")
    if host:
        return host
    return table.name[:80] if table.name else "unknown"


def merge_tables(tables: list[ExtractedTable]) -> ExtractedTable | None:
    if not tables:
        return None

    data_columns: list[str] = []
    for table in tables:
        for col in table.columns:
            key = col.strip()
            if not key or key in _SOURCE_COLS:
                continue
            if key not in data_columns:
                data_columns.append(key)

    master_columns = [_S_NO, "source", "source_url", *data_columns]
    master_rows: list[list[str]] = []
    serial = 0

    for table in tables:
        index = {c: i for i, c in enumerate(table.columns)}
        label = _source_label(table)
        for row in table.rows:
            serial += 1
            line = [str(serial), label, table.source_url]
            for col in data_columns:
                idx = index.get(col)
                if idx is None or idx >= len(row):
                    line.append("")
                else:
                    line.append(str(row[idx]).strip())
            master_rows.append(line)

    return ExtractedTable(
        name="Master dataset (all sources)",
        source_url="",
        columns=master_columns,
        rows=master_rows,
        row_count=len(master_rows),
    )


def _row_key(columns: list[str], row: list[str]) -> tuple[str, ...]:
    index = {c: i for i, c in enumerate(columns)}
    url = row[index["source_url"]] if "source_url" in index and index["source_url"] < len(row) else ""
    model_idx = index.get("model")
    model = ""
    if model_idx is not None and model_idx < len(row):
        model = row[model_idx].strip().lower()
    if not model:
        for col in columns:
            if col in _SOURCE_COLS or col == _S_NO:
                continue
            idx = index.get(col)
            if idx is not None and idx < len(row) and row[idx].strip():
                model = row[idx].strip().lower()
                break
    return (url.rstrip("/"), model)


def upsert_master_table(
    existing: ExtractedTable | None,
    incoming: ExtractedTable,
) -> tuple[ExtractedTable, int]:
    """Merge incoming scrape into stored master; refresh changed rows, append new ones."""
    fresh = incoming if incoming.columns and incoming.columns[0] == _S_NO else merge_tables([incoming])
    if fresh is None:
        return existing or ExtractedTable(name="Master", source_url="", columns=[_S_NO], rows=[], row_count=0), 0
    if existing is None or not existing.row_count:
        return fresh, fresh.row_count

    data_columns: list[str] = []
    for col in existing.columns + fresh.columns:
        if col in (_S_NO, "source", "source_url"):
            continue
        if col not in data_columns:
            data_columns.append(col)
    master_columns = [_S_NO, "source", "source_url", *data_columns]
    keyed: dict[tuple[str, ...], list[str]] = {}

    def ingest(table: ExtractedTable) -> None:
        idx = {c: i for i, c in enumerate(table.columns)}
        for row in table.rows:
            url = row[idx["source_url"]] if "source_url" in idx and idx["source_url"] < len(row) else ""
            label = row[idx["source"]] if "source" in idx and idx["source"] < len(row) else ""
            data = []
            for col in data_columns:
                cidx = idx.get(col)
                data.append(str(row[cidx]).strip() if cidx is not None and cidx < len(row) else "")
            line = ["0", label, url, *data]
            keyed[_row_key(master_columns, line)] = [label, url, *data]

    ingest(existing)
    before = len(keyed)
    ingest(fresh)
    new_keys = len(keyed) - before

    master_rows: list[list[str]] = []
    for serial, parts in enumerate(keyed.values(), start=1):
        label, url, *data = parts
        master_rows.append([str(serial), label, url, *data])

    merged = ExtractedTable(
        name=existing.name or fresh.name,
        source_url="",
        columns=master_columns,
        rows=master_rows,
        row_count=len(master_rows),
    )
    return merged, new_keys


def add_serial_numbers(table: ExtractedTable) -> ExtractedTable:
    """Prefix S. No. column on a single-source table."""
    if table.columns and table.columns[0] == _S_NO:
        return table
    rows = [[str(i + 1), *row] for i, row in enumerate(table.rows)]
    return ExtractedTable(
        name=table.name,
        source_url=table.source_url,
        columns=[_S_NO, *table.columns],
        rows=rows,
        row_count=len(rows),
    )
