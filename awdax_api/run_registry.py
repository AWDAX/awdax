from __future__ import annotations

import threading

_lock = threading.Lock()
_running: set[str] = set()
_job_to_instance: dict[str, str] = {}


def is_running(instance_id: str) -> bool:
    with _lock:
        return instance_id in _running


def mark_running(instance_id: str) -> None:
    with _lock:
        _running.add(instance_id)


def mark_stopped(instance_id: str) -> None:
    with _lock:
        _running.discard(instance_id)


def instance_for_job(job_id: str | None) -> str | None:
    if not job_id:
        return None
    with _lock:
        return _job_to_instance.get(job_id)


def register_job(instance_id: str, job_id: str | None) -> None:
    with _lock:
        if job_id:
            _job_to_instance[job_id] = instance_id


def unregister_job(instance_id: str, job_id: str | None) -> None:
    with _lock:
        if job_id and _job_to_instance.get(job_id) == instance_id:
            _job_to_instance.pop(job_id, None)


def active_regulatory_instances() -> set[str]:
    with _lock:
        return set(_running)
