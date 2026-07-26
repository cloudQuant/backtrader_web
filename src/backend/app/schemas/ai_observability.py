"""Schemas for AI provider call observability."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AICallStatus(str, Enum):
    """Supported AI call terminal statuses."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class AICallLogCreate(BaseModel):
    """Input payload for creating an AI call log record."""

    user_id: str | None = None
    request_id: str | None = None
    service_name: str = Field(..., min_length=1, max_length=50)
    mode: str = Field(..., min_length=1, max_length=50)
    model_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., min_length=1, max_length=50)
    prompt_template_id: str | None = Field(default=None, max_length=100)
    prompt_template_version: str | None = Field(default=None, max_length=50)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    status: AICallStatus
    error_code: str | None = Field(default=None, max_length=100)
    error_message: str | None = None
    response_chars: int = Field(default=0, ge=0)
    prompt_hash: str = Field(..., min_length=64, max_length=64)


class AICallLogRead(AICallLogCreate):
    """Serialized AI call log record."""

    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
