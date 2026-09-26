"""Create, list, and manage chat tracking instances."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.schemas import (
    CreateInstanceRequest,
    InstanceDetail,
    InstanceSummary,
    LiveToggleRequest,
    SendMessageRequest,
)
from live.manager import live_manager
from warehouse.database import get_db
from warehouse import instances as instance_store

router = APIRouter(prefix="/instances", tags=["instances"])


@router.get("", response_model=list[InstanceSummary])
def list_instances(db: Session = Depends(get_db)) -> list[InstanceSummary]:
    return instance_store.list_instances(db)


@router.post("", response_model=InstanceDetail, status_code=status.HTTP_201_CREATED)
def create_instance(
    body: CreateInstanceRequest | None = None,
    db: Session = Depends(get_db),
) -> InstanceDetail:
    title = (body.title if body and body.title else None) or instance_store.DEFAULT_TITLE
    instance = instance_store.create_instance(db, title=title)
    loaded = instance_store.get_instance(db, instance.id)
    assert loaded is not None
    return loaded


@router.get("/{instance_id}", response_model=InstanceDetail)
def get_instance(instance_id: str, db: Session = Depends(get_db)) -> InstanceDetail:
    instance = instance_store.get_instance(db, instance_id)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    return instance


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instance(instance_id: str, db: Session = Depends(get_db)) -> None:
    if not instance_store.delete_instance(db, instance_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")


@router.post("/{instance_id}/messages", response_model=InstanceDetail)
def send_message(
    instance_id: str,
    body: SendMessageRequest,
    db: Session = Depends(get_db),
) -> InstanceDetail:
    instance = instance_store.append_user_message(db, instance_id, body.text.strip())
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    live_manager.stop(instance_id)
    live_manager.start(instance_id)
    return instance


@router.patch("/{instance_id}/live", response_model=InstanceDetail)
def set_live(
    instance_id: str,
    body: LiveToggleRequest,
    db: Session = Depends(get_db),
) -> InstanceDetail:
    instance = instance_store.set_live_enabled(db, instance_id, body.enabled)
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
    if body.enabled and instance.goal_text:
        live_manager.start(instance_id)
    else:
        live_manager.stop(instance_id)
    loaded = instance_store.get_instance(db, instance_id)
    assert loaded is not None
    return loaded
