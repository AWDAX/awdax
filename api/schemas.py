"""Pydantic request/response models for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InstanceSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InstanceDetail(InstanceSummary):
    messages: list[MessageOut]
    live_enabled: bool = True
    dataset_row_count: int = 0


class LiveToggleRequest(BaseModel):
    enabled: bool


class CreateInstanceRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1)
