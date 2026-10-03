from __future__ import annotations

import os
import threading

DEFAULT_MAX_RUNS = 4
DEFAULT_MAX_RUNS_PER_USER = 2


class RunLimitError(Exception):
    """Too many concurrent runs (global or per user). Deliberately not a RuntimeError: callers treat
    RuntimeError as "this instance is already running" (HTTP 409)."""


_lock = threading.Lock()
_running: set[str] = set()
_owners: dict[str, str] = {}
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
        _owners.pop(instance_id, None)


def _limit(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _capacity_error(instance_id: str, owner: str) -> Exception | None:
    """Why a run can't start now, or None. Caller holds _lock."""
    if instance_id in _running:
        return RuntimeError("A run is already active for this instance")
    if len(_running) >= _limit("AWDAX_MAX_RUNS", DEFAULT_MAX_RUNS):
        return RunLimitError("Too many runs are active")
    if sum(1 for o in _owners.values() if o == owner) >= _limit("AWDAX_MAX_RUNS_PER_USER", DEFAULT_MAX_RUNS_PER_USER):
        return RunLimitError("Too many runs are active for this user")
    return None


def has_capacity(instance_id: str, user_id: str | None) -> bool:
    """Non-mutating pre-check, so a request that would be refused can be refused before it stops tracking,
    clears a dataset or saves anything. try_mark_running remains the atomic claim."""
    with _lock:
        return not isinstance(_capacity_error(instance_id, user_id or "anonymous"), RunLimitError)


def try_mark_running(instance_id: str, user_id: str | None) -> None:
    """Atomically claim a run slot. Raises RuntimeError if the instance is already running, otherwise
    RunLimitError when AWDAX_MAX_RUNS (global) or AWDAX_MAX_RUNS_PER_USER is reached. Limits are read per call."""
    owner = user_id or "anonymous"
    with _lock:
        error = _capacity_error(instance_id, owner)
        if error is not None:
            raise error
        _running.add(instance_id)
        _owners[instance_id] = owner


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
