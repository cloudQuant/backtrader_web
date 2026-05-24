"""
Audit API endpoints for user operation event tracking and querying.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import get_current_user
from app.schemas.audit import (
    AuditEventBatch,
    AuditQueryParams,
    AuditQueryResponse,
)
from app.schemas.auth import TokenPayload
from app.services.audit_service import AuditService

router = APIRouter()

_audit_service = AuditService()


def get_audit_service() -> AuditService:
    return _audit_service


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request headers or connection info."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.post("/events", status_code=status.HTTP_201_CREATED)
async def create_audit_events(
    batch: AuditEventBatch,
    request: Request,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """Batch upload user operation events.

    Requires authenticated user. Events are validated individually;
    invalid events are skipped without affecting valid ones.

    Args:
        batch: Batch of operation events (max 50).
        request: FastAPI request object.
        current_user: Authenticated user token payload.

    Returns:
        Dictionary with count of persisted events.
    """
    client_ip = _get_client_ip(request)
    persisted = await _audit_service.create_events(
        events=batch.events,
        user_id=str(current_user.sub),
        client_ip=client_ip,
    )
    return {"persisted": persisted, "total": len(batch.events)}


@router.get("/records", response_model=AuditQueryResponse)
async def query_audit_records(
    current_user: TokenPayload = Depends(get_current_user),
    user_id: str | None = Query(None, description="Filter by user ID"),
    event_type: str | None = Query(None, description="Filter by event type"),
    start_time: datetime | None = Query(None, description="Start time filter (ISO 8601)"),
    end_time: datetime | None = Query(None, description="End time filter (ISO 8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (1-100)"),
) -> AuditQueryResponse:
    """Query audit records with filters and pagination.

    Requires admin role. Supports filtering by user_id, event_type,
    and time range. Results are sorted by server_timestamp descending.

    Args:
        current_user: Authenticated user token payload.
        user_id: Optional user ID filter.
        event_type: Optional event type filter.
        start_time: Optional start time filter.
        end_time: Optional end time filter.
        page: Page number (1-based).
        page_size: Number of records per page.

    Returns:
        Paginated audit query response.

    Raises:
        HTTPException: 403 if user is not admin.
    """
    # Admin check
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to access audit records",
        )

    params = AuditQueryParams(
        user_id=user_id,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )

    return await _audit_service.query_records(params)
