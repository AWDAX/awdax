"""Background live workers (one thread per active instance)."""

from __future__ import annotations

import logging
import threading
import time

from config.settings import settings
from live import bus
from live.cycle import run_live_cycle
from live.types import LivePhase, LiveStatus
from warehouse.database import SessionLocal
from warehouse import instances as instance_store

logger = logging.getLogger(__name__)


class LiveManager:
    def __init__(self) -> None:
        self._stop: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def start(self, instance_id: str) -> None:
        with self._lock:
            if instance_id in self._threads and self._threads[instance_id].is_alive():
                return
            stop = threading.Event()
            self._stop[instance_id] = stop
            t = threading.Thread(
                target=self._loop,
                args=(instance_id, stop),
                name=f"awdax-live-{instance_id[:8]}",
                daemon=True,
            )
            self._threads[instance_id] = t
            t.start()

    def stop(self, instance_id: str) -> None:
        ev = self._stop.get(instance_id)
        if ev:
            ev.set()

    def stop_all(self) -> None:
        for instance_id in list(self._stop.keys()):
            self.stop(instance_id)

    def resume_all(self) -> None:
        db = SessionLocal()
        try:
            for row in instance_store.list_instances(db):
                if row.live_enabled and row.goal_text:
                    self.start(row.id)
        finally:
            db.close()

    def _loop(self, instance_id: str, stop: threading.Event) -> None:
        cycle = 0
        while not stop.is_set():
            db = SessionLocal()
            try:
                inst = instance_store.get_instance(db, instance_id)
                if inst is None or not inst.goal_text:
                    break
                if not inst.live_enabled:
                    status = LiveStatus(phase=LivePhase.STOPPED, live_enabled=False, detail="Live off")
                    instance_store.set_live_state(db, instance_id, status)
                    bus.publish(instance_id, status.model_dump())
                    break

                goal = inst.goal_text
                report_json = inst.report_snapshot_json
                master_json = inst.dataset_json
                cycle += 1

                def progress(phase: LivePhase, detail: str, source: str = "") -> None:
                    status = LiveStatus(
                        phase=phase,
                        detail=detail,
                        current_source=source,
                        cycle=cycle,
                        live_enabled=True,
                        rows_total=inst.dataset_row_count,
                    )
                    instance_store.set_live_state(db, instance_id, status)
                    instance_store.update_live_carrier(db, instance_id, _carrier_text(status))
                    db.commit()
                    bus.publish(
                        instance_id,
                        instance_store.live_event_payload(db, instance_id) or status.model_dump(),
                    )

                status = LiveStatus(
                    phase=LivePhase.DISCOVERY if not report_json else LivePhase.EXTRACT,
                    detail="Starting live cycle…",
                    cycle=cycle,
                    live_enabled=True,
                    rows_total=inst.dataset_row_count,
                )
                instance_store.set_live_state(db, instance_id, status)
                db.commit()
                bus.publish(
                    instance_id,
                    instance_store.live_event_payload(db, instance_id) or status.model_dump(),
                )

                try:
                    report_out, master_out, chat, rows_total, added = run_live_cycle(
                        goal,
                        report_json=report_json,
                        master_json=master_json,
                        progress=progress,
                    )
                except Exception as exc:
                    logger.exception("Live cycle failed for %s", instance_id)
                    err = LiveStatus(
                        phase=LivePhase.ERROR,
                        detail=str(exc)[:240],
                        cycle=cycle,
                        live_enabled=True,
                        rows_total=inst.dataset_row_count,
                    )
                    instance_store.set_live_state(db, instance_id, err)
                    instance_store.update_live_carrier(
                        db, instance_id, f"**Live error** — {exc}. Retrying…"
                    )
                    db.commit()
                    bus.publish(
                        instance_id,
                        instance_store.live_event_payload(db, instance_id, chat_updated=True)
                        or err.model_dump(),
                    )
                    self._sleep(stop, settings.live_error_retry_seconds)
                    continue

                instance_store.apply_cycle_result(
                    db,
                    instance_id,
                    report_json=report_out,
                    dataset_json=master_out,
                    row_count=rows_total,
                    chat_text=chat,
                    first_cycle=report_json is None,
                    rows_added=added,
                )
                idle = LiveStatus(
                    phase=LivePhase.SLEEP,
                    detail=f"Next refresh in {settings.live_refresh_interval_seconds}s",
                    cycle=cycle,
                    live_enabled=True,
                    rows_total=rows_total,
                    rows_added_last_cycle=added,
                )
                instance_store.set_live_state(db, instance_id, idle)
                db.commit()
                payload = (
                    instance_store.live_event_payload(
                        db, instance_id, include_dataset=True, chat_updated=True
                    )
                    or idle.model_dump()
                )
                bus.publish(instance_id, payload)
            finally:
                db.close()

            self._sleep(stop, settings.live_refresh_interval_seconds)

        with self._lock:
            self._stop.pop(instance_id, None)
            self._threads.pop(instance_id, None)

    @staticmethod
    def _sleep(stop: threading.Event, seconds: int) -> None:
        end = time.monotonic() + max(seconds, 1)
        while time.monotonic() < end:
            if stop.wait(timeout=1.0):
                return


def _carrier_text(status: LiveStatus) -> str:
    src = f" · **{status.current_source}**" if status.current_source else ""
    return (
        f"**Live** ({status.phase.value}) — {status.detail}{src}\n\n"
        f"_Fetching in the background; table updates below._"
    )


live_manager = LiveManager()
