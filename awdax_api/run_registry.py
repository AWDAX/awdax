from __future__ import annotations

import os
import threading

# Runs that may be active at once: in total on this server, and for one signed-in user. A run past either limit is refused
# with a 429. Each run can open several Chrome windows, so size these to the machine's memory (override in .env).
DEFAULT_MAX_RUNS = 10
DEFAULT_MAX_RUNS_PER_USER = 5


DEFAULT_MAX_QUEUE = 20  # runs that may wait for a free slot, across all users


class RunCancelled(Exception):
    """A run was stopped on purpose (the chat was paused or deleted); raised inside the run to unwind it."""


class RunLimitError(Exception):
    """Too many concurrent runs (global or per user). Deliberately not a RuntimeError: callers treat
    RuntimeError as "this instance is already running" (HTTP 409)."""


_lock = threading.Lock()
_running: set[str] = set()
_owners: dict[str, str] = {}
_job_to_instance: dict[str, str] = {}
_cancelled: set[str] = set()
_queue: list[str] = []  # instance ids waiting for a slot, oldest first
_queued: dict[str, tuple[str, dict]] = {}  # instance id -> (owner, what to start it with)


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
        _cancelled.discard(instance_id)


def request_cancel(instance_id: str) -> bool:
    """Ask the active run of this chat to stop at its next step. False when no run is active."""
    with _lock:
        if instance_id not in _running:
            return False
        _cancelled.add(instance_id)
        return True


def is_cancelled(instance_id: str) -> bool:
    with _lock:
        return instance_id in _cancelled


def check_cancelled(instance_id: str) -> None:
    if is_cancelled(instance_id):
        raise RunCancelled(instance_id)


# ---- waiting list: a run that finds no free slot waits here and starts when one frees up (first come, first served)


def _max_queue() -> int:
    return _limit("AWDAX_MAX_QUEUE", DEFAULT_MAX_QUEUE)


def enqueue(instance_id: str, user_id: str | None, payload: dict, *, front: bool = False) -> int:
    """Put a run on the waiting list; its place (1 = next). Raises RunLimitError when the list is full."""
    with _lock:
        if instance_id in _queued:
            return _queue.index(instance_id) + 1
        if len(_queue) >= _max_queue():
            raise RunLimitError("The waiting list is full")
        _queued[instance_id] = (user_id or "anonymous", payload)
        if front:
            _queue.insert(0, instance_id)
        else:
            _queue.append(instance_id)
        return _queue.index(instance_id) + 1


def dequeue(instance_id: str) -> bool:
    with _lock:
        if instance_id not in _queued:
            return False
        _queued.pop(instance_id, None)
        _queue.remove(instance_id)
        return True


def queue_position(instance_id: str) -> int | None:
    with _lock:
        return _queue.index(instance_id) + 1 if instance_id in _queued else None


def queued_ids() -> list[str]:
    with _lock:
        return list(_queue)


def pop_startable() -> tuple[str, str, dict] | None:
    """The first waiting run that fits now (a user at their own limit is passed over, not blocking the others)."""
    with _lock:
        for iid in _queue:
            owner, payload = _queued[iid]
            if _capacity_error(iid, owner) is None:
                _queue.remove(iid)
                _queued.pop(iid, None)
                return iid, owner, payload
    return None


def has_room(instance_id: str, user_id: str | None) -> bool:
    """A run can start now, or at least wait: only a full waiting list turns it away."""
    with _lock:
        if instance_id in _queued:
            return True
        error = _capacity_error(instance_id, user_id or "anonymous")
        return not isinstance(error, RunLimitError) or len(_queue) < _max_queue()


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
        _cancelled.discard(instance_id)


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
