"""Extract classic HTML <table> elements."""

from __future__ import annotations

from bs4 import BeautifulSoup

id = "html_tables"


def extract(html: str, url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows_out: list[dict[str, str]] = []
    for table in soup.find_all("table"):
        headers: list[str] = []
        trs = table.find_all("tr")
        if not trs:
            continue
        first_cells = trs[0].find_all(["th", "td"])
        if trs[0].find_all("th"):
            headers = [c.get_text(" ", strip=True) or f"col_{i}" for i, c in enumerate(first_cells)]
            data_rows = trs[1:]
        else:
            headers = [f"col_{i}" for i in range(len(first_cells))]
            data_rows = trs
        if not headers:
            continue
        for tr in data_rows[:200]:
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row: dict[str, str] = {}
            for i, cell in enumerate(cells):
                key = headers[i] if i < len(headers) else f"col_{i}"
                row[key] = cell.get_text(" ", strip=True)
            if any(v for v in row.values()):
                rows_out.append(row)
        if rows_out:
            break
    return rows_out
