"""Map hosts/methods to preexisting extractors."""

from __future__ import annotations

from urllib.parse import urlparse

from extractors import automotive_listing, html_tables

_EXTRACTORS = {
    html_tables.id: html_tables,
    automotive_listing.id: automotive_listing,
}

_HOST_DEFAULT = {
    "cardekho.com": automotive_listing.id,
    "carwale.com": automotive_listing.id,
    "zigwheels.com": automotive_listing.id,
    "autocarindia.com": automotive_listing.id,
    "91wheels.com": automotive_listing.id,
}


def host_extractor_id(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for suffix, ext_id in _HOST_DEFAULT.items():
        if host == suffix or host.endswith(f".{suffix}"):
            return ext_id
    return html_tables.id


def get_extractor(extractor_id: str):
    return _EXTRACTORS.get(extractor_id, html_tables)


def module_path(extractor_id: str) -> str:
    if extractor_id == automotive_listing.id:
        return "extractors/automotive_listing.py"
    return "extractors/html_tables.py"
