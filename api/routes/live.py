"""SSE: current fetch step and progress."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from live import bus
from warehouse.database import get_db
from warehouse import instances as instance_store

router = APIRouter(prefix="/instances", tags=["live"])


@router.get("/{instance_id}/live")
def get_live_snapshot(instance_id: str, db: Session = Depends(get_db)) -> dict:
    inst = instance_store.get_instance(db, instance_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    status = instance_store.get_live_status(db, instance_id)
    return {
        "live_enabled": inst.live_enabled,
        "status": status.model_dump() if status else {},
        "rows_total": inst.dataset_row_count,
    }


@router.get("/{instance_id}/live/stream")
async def live_stream(instance_id: str, db: Session = Depends(get_db)) -> StreamingResponse:
    if instance_store.get_instance(db, instance_id) is None:
        raise HTTPException(status_code=404, detail="Instance not found")

    queue = bus.register(instance_id)
    snap = instance_store.live_event_payload(db, instance_id, include_dataset=True)
    if snap:
        await queue.put(json.dumps(snap, default=str))

    async def event_generator():
        try:
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=25.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bus.unregister(instance_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
