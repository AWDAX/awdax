"""Heuristic listing parse for JS-heavy automotive pages."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

id = "automotive_listing"

_PRICE = re.compile(r"(₹[\d,.]+|[\d,.]+\s*lakh)", re.I)


def extract(html: str, url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if len(line) < 8 or len(line) > 220:
            continue
        if not _PRICE.search(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        model = line
        price_match = _PRICE.search(line)
        price = price_match.group(0) if price_match else ""
        if price and price in model:
            model = model.replace(price, "").strip(" -–|")
        rows.append({"model": model[:120], "price": price, "source_line": line[:200]})
        if len(rows) >= 150:
            break
    return rows
