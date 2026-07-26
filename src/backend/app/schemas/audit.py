"""
Audit event schemas for request/response validation.
"""

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class OperationEvent(BaseModel):
    """Single user operation event from frontend.

    Attributes:
        event_type: Type of event (click, navigation, etc.).
        event_target: Target element identifier.
        page_path: Page URL path where event occurred.
        event_data: Additional event metadata (max 10KB JSON).
        client_timestamp: Timestamp from client browser (ISO 8601).
        session_id: Browser session identifier.
    """

    event_type: str = Field(..., max_length=50)
    event_target: str | None = Field(None, max_length=200)
    page_path: str = Field(..., max_length=500)
    event_data: dict | None = None
    client_timestamp: datetime
    session_id: str | None = Field(None, max_length=64)

    @field_validator("event_data")
    @classmethod
    def validate_event_data_size(cls, v: dict | None) -> dict | None:
        """Validate that event_data JSON does not exceed 10KB."""
        if v is not None:
            serialized = json.dumps(v, ensure_ascii=False)
            if len(serialized.encode("utf-8")) > 10 * 1024:
                raise ValueError("event_data must not exceed 10KB")
        return v


class AuditEventBatch(BaseModel):
    """Batch of operation events for bulk upload.

    Attributes:
        events: List of operation events (max 50 per batch).
    """

    events: list[OperationEvent] = Field(..., max_length=50)


class AuditRecordResponse(BaseModel):
    """Audit record response DTO.

    Attributes:
        id: Record identifier.
        user_id: User who performed the action.
        session_id: Browser session identifier.
        event_type: Type of event.
        event_target: Target element identifier.
        page_path: Page URL path.
        event_data: Additional event data.
        client_timestamp: Client-side timestamp.
        server_timestamp: Server-side timestamp.
        client_ip: Client IP address.
    """

    id: str
    user_id: str
    session_id: str | None
    event_type: str
    event_target: str | None
    page_path: str
    event_data: dict | None
    client_timestamp: datetime
    server_timestamp: datetime
    client_ip: str | None

    model_config = {"from_attributes": True}


class AuditQueryParams(BaseModel):
    """Query parameters for audit record search.

    Attributes:
        user_id: Filter by user ID.
        event_type: Filter by event type.
        start_time: Filter records after this time (inclusive).
        end_time: Filter records before this time (inclusive).
        page: Page number (1-based).
        page_size: Number of records per page (1-100).
    """

    user_id: str | None = None
    event_type: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class AuditQueryResponse(BaseModel):
    """Paginated audit query response.

    Attributes:
        items: List of audit records.
        total_count: Total number of matching records.
        current_page: Current page number.
        total_pages: Total number of pages.
    """

    items: list[AuditRecordResponse]
    total_count: int
    current_page: int
    total_pages: int
