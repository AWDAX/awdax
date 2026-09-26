"""ORM models for chat instances (single-user platform for now)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ChatInstance(Base):
    __tablename__ = "chat_instances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), default="New track")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    goal_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    live_state_json: Mapped[str] = mapped_column(Text, default="{}")
    report_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_row_count: Mapped[int] = mapped_column(Integer, default=0)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_instances.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    is_live_carrier: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    instance: Mapped[ChatInstance] = relationship(back_populates="messages")
