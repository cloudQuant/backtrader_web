"""
Audit record ORM model for user operation tracking.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text

from app.db.database import Base


class AuditRecord(Base):
    """User operation audit record.

    Stores frontend user interaction events for compliance auditing
    and behavior analysis.

    Attributes:
        id: Unique record identifier (UUID).
        user_id: User who performed the action.
        session_id: Browser session identifier.
        event_type: Type of event (click, navigation, etc.).
        event_target: Target element identifier.
        page_path: Page URL path where event occurred.
        event_data: Additional event data as JSON string (max 10KB).
        client_timestamp: Timestamp from client browser.
        server_timestamp: Timestamp when server received the event.
        client_ip: Client IP address.
    """

    __tablename__ = "audit_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_target = Column(String(200), nullable=True)
    page_path = Column(String(500), nullable=False)
    event_data = Column(Text, nullable=True)
    client_timestamp = Column(DateTime, nullable=False)
    server_timestamp = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    client_ip = Column(String(45), nullable=True)

    __table_args__ = (
        Index("ix_audit_server_timestamp", "server_timestamp"),
        Index("ix_audit_user_timestamp", "user_id", "server_timestamp"),
    )
