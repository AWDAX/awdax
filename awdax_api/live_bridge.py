from __future__ import annotations

import logging
import queue
import threading
from typing import Any

from awdax_api.dataset_export import build_dataset_table
from awdax_api.run_registry import active_regulatory_instances, instance_for_job
from awdax_api.serializers import to_awdax_live_state
from awdax_api.session_store import load_instance_session, persist_run_state, set_awdax_run

logger = logging.getLogger(__name__)


class LiveBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._ws_clients: dict[str, list[Any]] = {}
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        from RegulatoryFeed import feed_service
        from scraper import universal_service

        threading.Thread(target=self._fan_in, args=(universal_service.subscribe_events(), "universal"), daemon=True).start()
        threading.Thread(target=self._fan_in, args=(feed_service.subscribe_events(), "regulatory"), daemon=True).start()

    def subscribe(self, instance_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._lock:
            self._subscribers.setdefault(instance_id, []).append(q)
        return q

    def unsubscribe(self, instance_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(instance_id, [])
            if q in subs:
                subs.remove(q)

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
        jid = event.get("job_id")
        if jid:
            iid = instance_for_job(jid)
            if iid:
                return iid
        if channel == "regulatory":
            active = active_regulatory_instances()
            if len(active) == 1:
                return next(iter(active))
            for iid in active:
                sess = load_instance_session(iid)
                if sess and sess.get("run_active"):
                    return iid
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

    def _handle_backend_event(self, event: dict[str, Any], channel: str) -> None:
        etype = event.get("type")
        instance_id = self._resolve_instance(event, channel)
        if not instance_id:
            return
        sess = load_instance_session(instance_id)
        if not sess:
            return

        if etype == "log":
            msg = str(event.get("message") or "")
            phase = "extracting" if channel == "universal" else "extracting"
            set_awdax_run(sess, phase=phase, detail=msg[:500])
            persist_run_state(sess)
            self.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
            return

        if etype == "status":
            phase = str(event.get("phase") or "extracting")
            set_awdax_run(sess, phase=phase, detail=str(event.get("message") or ""))
            persist_run_state(sess)
            self.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
            return

        if etype == "item" and event.get("item"):
            item = event["item"]
            table = build_dataset_table(sess, limit=5000)
            if not table:
                return
            cols = table["columns"]
            row_cells = []
            for c in cols:
                row_cells.append(str(item.get(c) or item.get(c.replace("_", " ")) or ""))
            if not any(row_cells):
                subj = item.get("subject") or item.get("Subject") or ""
                gid = item.get("gazette_id") or item.get("external_id") or ""
                mapping = {c: gid if c == "gazette_id" else subj for c in cols}
                row_cells = [str(mapping.get(c, "")) for c in cols]
            src = item.get("pdf_url") or item.get("source_url") or event.get("source_url") or ""
            rows_total = (table.get("row_count") or 0) + 1
            gid = item.get("gazette_id") or item.get("external_id") or ""
            set_awdax_run(sess, rows_total=rows_total, rows_added=1, phase="extracting", detail=f"Saved row {gid}")
            persist_run_state(sess)
            self.notify_instance(
                instance_id,
                {
                    "type": "rows",
                    "run_id": (sess.get("awdax_run") or {}).get("id", ""),
                    "lane": "fast",
                    "source_url": src,
                    "columns": cols,
                    "rows": [row_cells],
                    "records": table.get("records") or [],
                    "partial_added": 0,
                    "accepted_total": rows_total,
                },
            )
            return

        if etype == "table":
            persist_run_state(sess)
            self.notify_instance(instance_id, {"type": "batch_complete"})


live_bridge = LiveBridge()
