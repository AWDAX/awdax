"""Thread-safe live event fan-out for SSE clients."""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from typing import Any

_lock = threading.Lock()
_queues: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def publish(instance_id: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, default=str)
    with _lock:
        queues = list(_queues.get(instance_id, []))
    if not queues or _loop is None:
        return
    for q in queues:
        try:
            _loop.call_soon_threadsafe(q.put_nowait, data)
        except RuntimeError:
            pass


def register(instance_id: str) -> asyncio.Queue[str]:
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
    with _lock:
        _queues[instance_id].append(q)
    return q


def unregister(instance_id: str, q: asyncio.Queue[str]) -> None:
    with _lock:
        lst = _queues.get(instance_id, [])
        if q in lst:
            lst.remove(q)
