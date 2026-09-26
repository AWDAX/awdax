"""Live tracking state exposed to the UI."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class LivePhase(str, Enum):
    IDLE = "idle"
    DISCOVERY = "discovery"
    INSPECT = "inspect"
    EXTRACT = "extract"
    MERGE = "merge"
    SLEEP = "sleep"
    ERROR = "error"
    STOPPED = "stopped"


class LiveStatus(BaseModel):
    phase: LivePhase = LivePhase.IDLE
    detail: str = ""
    current_source: str = ""
    rows_total: int = 0
    rows_added_last_cycle: int = 0
    cycle: int = 0
    live_enabled: bool = True
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def touch(
        self,
        *,
        phase: LivePhase | None = None,
        detail: str | None = None,
        current_source: str | None = None,
        rows_total: int | None = None,
        rows_added_last_cycle: int | None = None,
        cycle: int | None = None,
        live_enabled: bool | None = None,
    ) -> LiveStatus:
        data = self.model_dump()
        if phase is not None:
            data["phase"] = phase
        if detail is not None:
            data["detail"] = detail
        if current_source is not None:
            data["current_source"] = current_source
        if rows_total is not None:
            data["rows_total"] = rows_total
        if rows_added_last_cycle is not None:
            data["rows_added_last_cycle"] = rows_added_last_cycle
        if cycle is not None:
            data["cycle"] = cycle
        if live_enabled is not None:
            data["live_enabled"] = live_enabled
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return LiveStatus.model_validate(data)
