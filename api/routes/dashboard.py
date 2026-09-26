"""Dashboard data: live master table per instance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from warehouse.database import get_db
from warehouse import instances as instance_store

router = APIRouter(prefix="/instances", tags=["dashboard"])


@router.get("/{instance_id}/dashboard")
def get_dashboard(instance_id: str, db: Session = Depends(get_db)) -> dict:
    inst = instance_store.get_instance(db, instance_id)
    if inst is None:
        raise HTTPException(status_code=404, detail="Instance not found")
    dataset = instance_store.get_dataset(db, instance_id)
    return {
        "rows_total": inst.dataset_row_count,
        "table": dataset,
        "updated_at": inst.updated_at.isoformat() if inst.updated_at else None,
    }
