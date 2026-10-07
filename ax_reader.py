"""
Read a page the way a screen reader does: from the browser's accessibility tree.

The HTML digest the pipeline used to give the model loses what the browser knows (a title shown as "A Light in the ..." keeps its full
text in an attribute, which the tree uses as the link's name), is huge for JavaScript pages (60,000 tokens of app data for a ten-row table) and
shows nothing to click. The tree is small, names every control (including "Go to next page"), and each node can be clicked through
Chrome, which is what lets a run go past page 1 on a site that has a pager but no data feed.
See docs/AX_TREE_EXPERIMENT.md for the measurements.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Roles the tree prints no line for: their children are still read.
_SKIP_ROLES = {"none", "presentation", "generic", "InlineTextBox", "LineBreak", "ListMarker", "RootWebArea", "WebArea"}
# Page furniture: menus, headers, footers and side panels. Left out so the model reads the content.
LANDMARKS = {"navigation", "banner", "contentinfo", "complementary"}
_KEEP_EMPTY = {"table", "grid", "row", "cell", "gridcell", "columnheader", "rowheader", "list", "listitem", "article"}
_CELLS = {"cell", "gridcell", "columnheader", "rowheader"}

# What a person presses to see more: "Next", "Go to next page", an arrow, "Load more".
_MORE = re.compile(r"^(?:go to )?next(?: page)?\b|^older\b|^(?:load|show|view) more\b|^more results\b|^[›»>→]+$|^next\s*[›»>→]", re.I)


def _val(x: Any) -> Any:
    return x.get("value") if isinstance(x, dict) else None


def _role(n: dict[str, Any]) -> str:
    return str(_val(n.get("role")) or "")


def _name(n: dict[str, Any]) -> str:
    return str(_val(n.get("name")) or "").strip()


def _disabled(n: dict[str, Any]) -> bool:
    return any(p.get("name") == "disabled" and _val(p.get("value")) is True for p in n.get("properties") or [])


def nodes(driver: Any) -> list[dict[str, Any]]:
    """The page's accessibility tree, as Chrome reports it (a flat list of nodes with child ids)."""
    driver.execute_cdp_cmd("Accessibility.enable", {})
    return driver.execute_cdp_cmd("Accessibility.getFullAXTree", {}).get("nodes", [])


def tree_text(ax: list[dict[str, Any]], *, skip_landmarks: bool = True, max_chars: int | None = None) -> str:
    """The tree as compact text: a table row on one line (`row: a | b | c`), a list item or card on one line, controls by role and name.
    Menus, headers and footers are left out (and put back when that would leave almost nothing)."""
    if not ax:
        return ""
    text = _render(ax, skip_landmarks)
    if skip_landmarks and len(text.strip()) < 50:
        text = _render(ax, False)
    limit = max_chars if max_chars is not None else int(os.getenv("AX_MAX_CHARS", "120000"))
    return text[:limit] if len(text) > limit else text


def _render(ax: list[dict[str, Any]], skip_landmarks: bool) -> str:
    by_id = {n["nodeId"]: n for n in ax}
    root = next((n for n in ax if not n.get("parentId")), ax[0])
    lines: list[str] = []

    def words(nid: str, seen: tuple[str, ...]) -> list[str]:
        """The words under a node in order, without repeating what a parent's name already says."""
        n = by_id.get(nid)
        if not n:
            return []
        out: list[str] = []
        role, name = _role(n), _name(n)
        if not n.get("ignored") and name and role not in _SKIP_ROLES:
            if not any(name in s for s in seen):
                out.append(name)
            seen = seen + (name,)
        for c in n.get("childIds") or []:
            out += words(c, seen)
        return out

    def walk(nid: str, depth: int) -> None:
        n = by_id.get(nid)
        if not n:
            return
        role, name = _role(n), _name(n)
        if skip_landmarks and role in LANDMARKS:
            return
        if n.get("ignored") or role in _SKIP_ROLES:
            for c in n.get("childIds") or []:
                walk(c, depth)
            return
        pad = "  " * depth
        if role == "row":
            cells = [" ".join(words(c, ())).strip() for c in n.get("childIds") or [] if by_id.get(c) and _role(by_id[c]) in _CELLS]
            if any(cells):
                lines.append(f"{pad}row: " + " | ".join(cells))
            return
        if role == "listitem":
            t = " ".join(words(nid, ())).strip()
            if t:
                lines.append(f"{pad}- {t}")
            return
        if role == "article":
            t = " ; ".join(w for w in words(nid, ()) if w)
            if t:
                lines.append(f"{pad}article: {t}")
            return
        if role == "StaticText":
            if name:
                lines.append(f"{pad}{name}")
            return
        if role in ("list", "table", "grid") and not name:
            lines.append(f"{pad}{role}")
            for c in n.get("childIds") or []:
                walk(c, depth + 1)
            return
        if name or role in ("heading", "button", "link", "textbox", "combobox", "tab"):
            lines.append(f"{pad}{role}" + (f' "{name[:300]}"' if name else ""))
        for c in n.get("childIds") or []:
            walk(c, depth + (1 if name else 0))

    walk(root["nodeId"], 0)
    return "\n".join(lines)


def item_estimate(text: str) -> int:
    """How many items the page lists: table rows (not the header), cards, or list items. 0 for an article or a menu."""
    lines = text.splitlines()
    rows = sum(1 for ln in lines if ln.lstrip().startswith("row:"))
    articles = sum(1 for ln in lines if ln.lstrip().startswith("article:"))
    items = sum(1 for ln in lines if ln.lstrip().startswith("- "))
    return max(rows - 1 if rows > 1 else 0, articles, items if items >= 5 else 0)


def pager_target(ax: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The control that shows the next part of the list: the last enabled button or link named like "Next", "Go to next page",
    an arrow or "Load more" (the last, because a pager sits after the list it pages)."""
    found = [n for n in ax if not n.get("ignored") and _role(n) in ("button", "link") and not _disabled(n)
             and _MORE.search(_name(n)) and "backendDOMNodeId" in n]
    return found[-1] if found else None


def signature(ax: list[dict[str, Any]]) -> str:
    return hashlib.sha1(tree_text(ax).encode("utf-8", "ignore")).hexdigest()


def click(driver: Any, node: dict[str, Any]) -> None:
    """Press a node of the tree through Chrome."""
    obj = driver.execute_cdp_cmd("DOM.resolveNode", {"backendNodeId": node["backendDOMNodeId"]})["object"]["objectId"]
    driver.execute_cdp_cmd("Runtime.callFunctionOn", {"objectId": obj, "functionDeclaration": "function(){ this.click(); }"})


def advance(driver: Any, ax: list[dict[str, Any]], target: dict[str, Any], *, wait_s: float = 15.0) -> bool:
    """Press the pager and wait until the page's content changes. False when it never does (the end of the list)."""
    before = signature(ax)
    try:
        click(driver, target)
    except Exception as e:  # noqa: BLE001 - a control that cannot be pressed ends the walk
        logger.info("Pager could not be pressed: %s", e)
        return False
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(0.7)
        try:
            if signature(nodes(driver)) != before:
                from inspector import wait_until_settled

                wait_until_settled(driver, max_s=6, min_s=0.5)
                return True
        except Exception:  # noqa: BLE001 - the page is navigating: look again
            continue
    return False


def row_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", str(v or "")).strip().lower() for v in row.values())


def fresh_rows(rows: Iterable[dict[str, Any]], seen: set[tuple[str, ...]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        k = row_key(r)
        if k not in seen and any(k):
            seen.add(k)
            out.append(r)
    return out
