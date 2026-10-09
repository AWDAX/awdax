from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

from awdax_api.dataset_export import build_dataset_table
from awdax_api.run_registry import instance_for_job
from awdax_api.serializers import to_awdax_live_state
from awdax_api.session_store import load_instance_session, run_finished, set_awdax_run, update_instance

logger = logging.getLogger(__name__)

# Each open live stream (SSE or WebSocket) holds a server thread for as long as it stays open: a few hundred tabs
# would exhaust them. Generous for real use (a chat open in a few tabs), small enough that one user can't.
MAX_STREAMS_PER_CHAT = 6
MAX_STREAMS_PER_USER = 16

ROW_REFRESH_S = 2.0  # how often a streamed row refreshes the table and saves the chat; rows in between are counted


class LiveBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._owner_of: dict[int, str] = {}  # id(queue) -> user, for the per-user count
        self._per_user: dict[str, int] = {}
        self._ws_clients: dict[str, list[Any]] = {}
        self._started = False
        self._row_cache: dict[str, dict[str, Any]] = {}

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        from RegulatoryFeed import feed_service
        from scraper import universal_service

        threading.Thread(target=self._fan_in, args=(universal_service.subscribe_events(), "universal"), daemon=True).start()
        threading.Thread(target=self._fan_in, args=(feed_service.subscribe_events(), "regulatory"), daemon=True).start()

    def subscribe(self, instance_id: str, owner: str | None = None) -> queue.Queue | None:
        """A queue of this chat's live messages, or None when `owner` already holds too many streams (or the chat
        has too many). Internal callers pass no owner and are never capped."""
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            subs = self._subscribers.setdefault(instance_id, [])
            if owner is not None:
                if len(subs) >= MAX_STREAMS_PER_CHAT or self._per_user.get(owner, 0) >= MAX_STREAMS_PER_USER:
                    return None
                self._per_user[owner] = self._per_user.get(owner, 0) + 1
                self._owner_of[id(q)] = owner
            subs.append(q)
        return q

    def unsubscribe(self, instance_id: str, q: queue.Queue) -> None:
        """Safe to call more than once for the same queue."""
        with self._lock:
            subs = self._subscribers.get(instance_id, [])
            if q in subs:
                subs.remove(q)
            owner = self._owner_of.pop(id(q), None)
            if owner is not None:
                left = self._per_user.get(owner, 1) - 1
                if left > 0:
                    self._per_user[owner] = left
                else:
                    self._per_user.pop(owner, None)

    def add_ws(self, instance_id: str, ws: Any) -> None:
        with self._lock:
            self._ws_clients.setdefault(instance_id, []).append(ws)

    def remove_ws(self, instance_id: str, ws: Any) -> None:
        with self._lock:
            clients = self._ws_clients.get(instance_id, [])
            if ws in clients:
                clients.remove(ws)

    def notify_instance(self, instance_id: str, message: dict[str, Any]) -> None:
        with self._lock:
            for q in list(self._subscribers.get(instance_id, [])):
                try:
                    q.put_nowait(message)
                except queue.Full:
                    pass

    def hello_payload(self, instance_id: str) -> dict[str, Any]:
        sess = load_instance_session(instance_id)
        if not sess:
            return {"type": "hello", "state": {"enabled": False, "latest_run": None, "rows_total": 0}, "events": []}
        return {
            "type": "hello",
            "state": to_awdax_live_state(sess),
            "events": list(sess.get("run_events") or [])[-12:],
        }

    def _resolve_instance(self, event: dict[str, Any], channel: str) -> str | None:
        """The one chat an event belongs to: the chat that started the scrape (eGazette events carry its id) or the
        chat that owns the job. An event that names neither is dropped; guessing "the running chat" would hand one
        user's progress and rows to another."""
        iid = event.get("instance_id")
        if iid:
            return str(iid)
        jid = event.get("job_id")
        if jid:
            return instance_for_job(jid)
        return None

    def _fan_in(self, sub: queue.Queue, channel: str) -> None:
        while True:
            try:
                event = sub.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._handle_backend_event(event, channel)
            except Exception as e:
                logger.warning("live_bridge event error: %s", e)

    def _handle_item(self, instance_id: str, event: dict[str, Any]) -> None:
        """One stored row, announced. The dataset table is rebuilt (and the chat saved) at most every ROW_REFRESH_S seconds
        and counted in between: rebuilding the whole table for every row made storing 5,000 rows cost about 10 minutes of
        CPU in this thread, slowing the scrape itself."""
        item = event["item"]
        now = time.monotonic()
        with self._lock:
            ctx = self._row_cache.get(instance_id)
            fresh = ctx is not None and now - ctx["at"] < ROW_REFRESH_S
            if fresh:
                ctx["count"] += 1
        if not fresh:
            sess = load_instance_session(instance_id)
            if not sess:
                return
            table = build_dataset_table(sess, limit=5000)
            if not table:
                return
            ctx = {"at": now, "cols": table["columns"], "count": (table.get("row_count") or 0) + 1, "records": table.get("records") or []}
            with self._lock:
                self._row_cache[instance_id] = ctx
        cols, rows_total = ctx["cols"], ctx["count"]
        row_cells = [str(item.get(c) or item.get(c.replace("_", " ")) or "") for c in cols]
        if not any(row_cells):
            subj = item.get("subject") or item.get("Subject") or ""
            gid = item.get("gazette_id") or item.get("external_id") or ""
            mapping = {c: gid if c == "gazette_id" else subj for c in cols}
            row_cells = [str(mapping.get(c, "")) for c in cols]
        src = item.get("pdf_url") or item.get("source_url") or event.get("source_url") or ""
        gid = item.get("gazette_id") or item.get("external_id") or ""
        run_id = ctx.get("run_id", "")
        if not fresh:

            def change(stored: dict[str, Any]) -> None:
                run = stored.get("awdax_run") or {}
                if run_finished(stored):
                    set_awdax_run(stored, status=run.get("status"), phase=run.get("phase") or "complete", detail=run.get("detail") or "", rows_total=rows_total, rows_added=1)
                else:
                    set_awdax_run(stored, rows_total=rows_total, rows_added=1, phase="extracting", detail=f"Saved row {gid}")

            sess = update_instance(instance_id, change)
            if sess is None:
                return
            run_id = ctx["run_id"] = (sess.get("awdax_run") or {}).get("id", "")
        self.notify_instance(
            instance_id,
            {
                "type": "rows",
                "run_id": run_id,
                "lane": "fast",
                "source_url": src,
                "columns": cols,
                "rows": [row_cells],
                "records": [] if fresh else ctx["records"],
                "partial_added": 0,
                "accepted_total": rows_total,
            },
        )

    def _handle_backend_event(self, event: dict[str, Any], channel: str) -> None:
        etype = event.get("type")
        instance_id = self._resolve_instance(event, channel)
        if not instance_id:
            return
        if etype == "item" and event.get("item"):
            self._handle_item(instance_id, event)  # before any session load: one of these arrives per stored row
            return
        sess = load_instance_session(instance_id)
        if not sess:
            return

        if etype in ("log", "status"):
            phase = "extracting" if etype == "log" else str(event.get("phase") or "extracting")
            detail = str(event.get("message") or "")[:500]

            def change(stored: dict[str, Any]) -> None:
                # A late event of a finished pass must not turn it back into "running".
                if not run_finished(stored):
                    set_awdax_run(stored, phase=phase, detail=detail)

            sess = update_instance(instance_id, change) or sess
            self.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
            return

        if etype == "table":
            self.notify_instance(instance_id, {"type": "batch_complete"})


live_bridge = LiveBridge()
