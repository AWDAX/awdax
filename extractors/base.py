"""Extractor plugin interface."""

from __future__ import annotations

from typing import Protocol


class TableExtractor(Protocol):
    id: str

    def extract(self, html: str, url: str) -> list[dict[str, str]]: ...
