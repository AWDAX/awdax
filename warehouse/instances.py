"""CRUD for chat tracking instances."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from live.types import LivePhase, LiveStatus
from warehouse.models import ChatInstance, ChatMessage, utcnow

DEFAULT_TITLE = "New track"


def list_instances(db: Session) -> list[ChatInstance]:
    stmt = select(ChatInstance).order_by(ChatInstance.updated_at.desc())
    return list(db.scalars(stmt).all())


def get_instance(db: Session, instance_id: str) -> ChatInstance | None:
    stmt = (
        select(ChatInstance)
        .where(ChatInstance.id == instance_id)
        .options(selectinload(ChatInstance.messages))
    )
    return db.scalars(stmt).first()


def create_instance(db: Session, *, title: str = DEFAULT_TITLE) -> ChatInstance:
    instance = ChatInstance(title=title, live_enabled=True)
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def delete_instance(db: Session, instance_id: str) -> bool:
    instance = db.get(ChatInstance, instance_id)
    if instance is None:
        return False
    db.delete(instance)
    db.commit()
    return True


def _title_from_first_message(current_title: str, user_text: str) -> str:
    if current_title != DEFAULT_TITLE or not user_text:
        return current_title
    if len(user_text) > 42:
        return f"{user_text[:42]}…"
    return user_text


def set_live_state(db: Session, instance_id: str, status: LiveStatus) -> None:
    instance = db.get(ChatInstance, instance_id)
    if instance is None:
        return
    instance.live_state_json = status.model_dump_json()
    instance.updated_at = utcnow()


def update_live_carrier(db: Session, instance_id: str, text: str) -> None:
    instance = get_instance(db, instance_id)
    if instance is None:
        return
    carrier = _live_carrier(instance)
    if carrier:
        carrier.text = text
    else:
        db.add(
            ChatMessage(
                instance_id=instance_id,
                role="bot",
                text=text,
                is_live_carrier=True,
            )
        )
    instance.updated_at = utcnow()


def _live_carrier(instance: ChatInstance) -> ChatMessage | None:
    for msg in reversed(instance.messages):
        if msg.role == "bot" and msg.is_live_carrier:
            return msg
    return None


def apply_cycle_result(
    db: Session,
    instance_id: str,
    *,
    report_json: str | None,
    dataset_json: str | None,
    row_count: int,
    chat_text: str,
    first_cycle: bool,
    rows_added: int = 0,
) -> None:
    instance = get_instance(db, instance_id)
    if instance is None:
        return
    if report_json:
        instance.report_snapshot_json = report_json
    if dataset_json:
        instance.dataset_json = dataset_json
    instance.dataset_row_count = row_count
    instance.updated_at = utcnow()

    carrier = _live_carrier(instance)
    if first_cycle and carrier:
        carrier.text = chat_text
        carrier.is_live_carrier = False
    elif first_cycle:
        db.add(ChatMessage(instance_id=instance_id, role="bot", text=chat_text))
    elif rows_added > 0:
        db.add(ChatMessage(instance_id=instance_id, role="bot", text=chat_text))
    if carrier and not first_cycle:
        carrier.text = (
            f"**Live** — {row_count} rows in dataset. "
            f"_Background refresh running…_"
        )


def set_live_enabled(db: Session, instance_id: str, enabled: bool) -> ChatInstance | None:
    instance = get_instance(db, instance_id)
    if instance is None:
        return None
    instance.live_enabled = enabled
    status = LiveStatus.model_validate_json(instance.live_state_json or "{}")
    phase = LivePhase.STOPPED if not enabled else status.phase
    detail = "Live paused" if not enabled else status.detail
    status = status.touch(live_enabled=enabled, phase=phase, detail=detail)
    instance.live_state_json = status.model_dump_json()
    instance.updated_at = utcnow()
    db.commit()
    return get_instance(db, instance_id)


def append_user_message(db: Session, instance_id: str, user_text: str) -> ChatInstance | None:
    instance = get_instance(db, instance_id)
    if instance is None:
        return None

    db.add(ChatMessage(instance_id=instance_id, role="user", text=user_text))
    instance.goal_text = user_text.strip()
    instance.live_enabled = True
    instance.report_snapshot_json = None
    instance.dataset_json = None
    instance.dataset_row_count = 0
    instance.title = _title_from_first_message(instance.title, user_text)

    for msg in list(instance.messages):
        if msg.is_live_carrier:
            db.delete(msg)

    db.add(
        ChatMessage(
            instance_id=instance_id,
            role="bot",
            text=(
                "**Live on** — discovery and extraction started.\n\n"
                "_Status updates appear above the table; this message fills in when the first pass completes._"
            ),
            is_live_carrier=True,
        )
    )
    status = LiveStatus(phase=LivePhase.DISCOVERY, detail="Queued…", live_enabled=True)
    instance.live_state_json = status.model_dump_json()
    instance.updated_at = utcnow()
    db.commit()
    return get_instance(db, instance_id)


def get_live_status(db: Session, instance_id: str) -> LiveStatus | None:
    instance = db.get(ChatInstance, instance_id)
    if instance is None:
        return None
    try:
        return LiveStatus.model_validate(json.loads(instance.live_state_json or "{}"))
    except Exception:
        return LiveStatus(live_enabled=instance.live_enabled)


def live_event_payload(
    db: Session,
    instance_id: str,
    *,
    include_dataset: bool = False,
    chat_updated: bool = False,
) -> dict | None:
    inst = db.get(ChatInstance, instance_id)
    if inst is None:
        return None
    status = get_live_status(db, instance_id)
    payload: dict = {
        "live_enabled": inst.live_enabled,
        "status": status.model_dump() if status else {},
        "rows_total": inst.dataset_row_count,
    }
    if include_dataset and inst.dataset_json:
        payload["dataset"] = get_dataset(db, instance_id)
    if chat_updated:
        payload["chat_updated"] = True
    return payload


def get_live_snapshot_payload(db: Session, instance_id: str) -> dict | None:
    return live_event_payload(db, instance_id, include_dataset=True)


def get_dataset(db: Session, instance_id: str) -> dict | None:
    instance = db.get(ChatInstance, instance_id)
    if instance is None or not instance.dataset_json:
        return None
    return json.loads(instance.dataset_json)
