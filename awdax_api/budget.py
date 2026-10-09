"""Per-user budgets for actions that cost model calls and browser time (new chats, runs, questions)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class Budget:
    """At most `limit` actions per user in any `window_s` seconds.

    ponytail: in this process only; a shared store (Redis) if the backend ever runs as several workers."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def spend(self, user: str) -> bool:
        """Record one action for `user`; False (and nothing recorded) when the budget is used up."""
        now = time.monotonic()
        with self._lock:
            q = self._recent[user]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True
