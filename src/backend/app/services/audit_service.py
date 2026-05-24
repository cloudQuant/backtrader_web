"""
Audit service for user operation event persistence and lifecycle management.
"""

import asyncio
import json
import math
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db.session_provider import unit_of_work
from app.models.audit_record import AuditRecord
from app.schemas.audit import (
    AuditQueryParams,
    AuditQueryResponse,
    AuditRecordResponse,
    OperationEvent,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)
_AuditBatch = tuple[list[AuditRecord], str]


class AuditService:
    """Service for audit event validation, persistence, and lifecycle management."""

    def __init__(self) -> None:
        """Initialize the AuditService."""
        self._settings = get_settings()
        self._queue_maxsize = getattr(self._settings, "AUDIT_QUEUE_MAXSIZE", 1000)
        self._queue: asyncio.Queue[_AuditBatch | None] = asyncio.Queue(maxsize=self._queue_maxsize)
        self._worker_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._worker_task is not None and not self._worker_task.done():
                return
            self._queue = asyncio.Queue(maxsize=self._queue_maxsize)
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("Audit async sink started")

    async def flush(self) -> None:
        if self._worker_task is None:
            return
        await self._queue.join()

    async def shutdown(self) -> None:
        async with self._lifecycle_lock:
            worker_task = self._worker_task
            if worker_task is None:
                return
            await self._queue.join()
            await self._queue.put(None)
            await worker_task
            self._worker_task = None
            self._queue = asyncio.Queue(maxsize=self._queue_maxsize)
            logger.info("Audit async sink shut down")

    async def create_events(
        self,
        events: list[OperationEvent],
        user_id: str,
        client_ip: str,
    ) -> int:
        """Validate and persist a batch of operation events.

        Each event is validated independently. Invalid events are skipped
        with a warning log. Valid events are persisted in a single transaction.

        Args:
            events: List of operation events to persist.
            user_id: ID of the user who generated the events.
            client_ip: Client IP address.

        Returns:
            Number of successfully persisted events.
        """
        now = datetime.now(timezone.utc)
        max_size_kb = getattr(self._settings, "AUDIT_EVENT_MAX_SIZE_KB", 10)
        valid_records: list[AuditRecord] = []

        for event in events:
            # Validate required fields
            if not event.event_type or not event.page_path:
                logger.warning(
                    f"Audit event validation failed: missing required fields. "
                    f"user_id={user_id} event_type={event.event_type}",
                )
                continue

            # Validate client_timestamp range (±24 hours)
            time_diff = abs((event.client_timestamp - now).total_seconds())
            if time_diff > 86400:  # 24 hours
                logger.warning(
                    f"Audit event validation failed: client_timestamp out of range. "
                    f"user_id={user_id} event_type={event.event_type}",
                )
                continue

            # Validate event_data size
            event_data_str = None
            if event.event_data is not None:
                event_data_str = json.dumps(event.event_data, ensure_ascii=False)
                if len(event_data_str.encode("utf-8")) > max_size_kb * 1024:
                    logger.warning(
                        f"Audit event validation failed: event_data exceeds {max_size_kb}KB. "
                        f"user_id={user_id} event_type={event.event_type}",
                    )
                    continue

            record = AuditRecord(
                user_id=user_id,
                session_id=event.session_id,
                event_type=event.event_type,
                event_target=event.event_target,
                page_path=event.page_path,
                event_data=event_data_str,
                client_timestamp=event.client_timestamp,
                server_timestamp=now,
                client_ip=client_ip,
            )
            valid_records.append(record)

        if not valid_records:
            return 0

        await self.start()
        try:
            self._queue.put_nowait((valid_records, user_id))
        except asyncio.QueueFull:
            logger.warning(
                f"Audit sink queue is full, dropping batch. "
                f"batch_size={len(valid_records)} user_id={user_id}",
            )
            return 0
        return len(valid_records)

    async def _worker_loop(self) -> None:
        while True:
            batch = await self._queue.get()
            try:
                if batch is None:
                    return
                records, user_id = batch
                try:
                    await self._persist_with_retry(records, user_id)
                except Exception as exc:
                    logger.error(
                        f"Audit async sink failed. batch_size={len(records)} "
                        f"user_id={user_id} error={exc}",
                    )
            finally:
                self._queue.task_done()

    async def _persist_with_retry(
        self, records: list[AuditRecord], user_id: str, max_retries: int = 3
    ) -> int:
        """Persist records with exponential backoff retry.

        Args:
            records: List of AuditRecord instances to persist.
            user_id: User ID for error logging.
            max_retries: Maximum number of retry attempts.

        Returns:
            Number of persisted records (0 if all retries failed).
        """
        delay = 0.1  # 100ms initial delay
        for attempt in range(max_retries):
            try:
                async with unit_of_work() as session:
                    session.add_all(records)
                    await session.flush()
                return len(records)
            except Exception as exc:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Audit persist attempt {attempt + 1} failed, retrying in {delay}s: {exc}",
                    )
                    await asyncio.sleep(delay)
                    delay *= 2  # Exponential backoff: 100ms → 200ms → 400ms
                else:
                    logger.error(
                        f"Audit persist failed after {max_retries} attempts. "
                        f"batch_size={len(records)} user_id={user_id} error={exc}",
                    )
        return 0

    async def query_records(self, params: AuditQueryParams) -> AuditQueryResponse:
        """Query audit records with filters and pagination.

        Args:
            params: Query parameters including filters and pagination.

        Returns:
            Paginated query response with matching records.
        """
        async with unit_of_work() as session:
            # Build base query
            query = select(AuditRecord)
            count_query = select(func.count(AuditRecord.id))

            # Apply filters
            if params.user_id:
                query = query.where(AuditRecord.user_id == params.user_id)
                count_query = count_query.where(AuditRecord.user_id == params.user_id)
            if params.event_type:
                query = query.where(AuditRecord.event_type == params.event_type)
                count_query = count_query.where(AuditRecord.event_type == params.event_type)
            if params.start_time:
                query = query.where(AuditRecord.server_timestamp >= params.start_time)
                count_query = count_query.where(
                    AuditRecord.server_timestamp >= params.start_time
                )
            if params.end_time:
                query = query.where(AuditRecord.server_timestamp <= params.end_time)
                count_query = count_query.where(
                    AuditRecord.server_timestamp <= params.end_time
                )

            # Get total count
            total_result = await session.execute(count_query)
            total_count = total_result.scalar() or 0

            # Apply ordering and pagination
            offset = (params.page - 1) * params.page_size
            query = (
                query.order_by(AuditRecord.server_timestamp.desc())
                .offset(offset)
                .limit(params.page_size)
            )

            result = await session.execute(query)
            records = result.scalars().all()

            # Build response items
            items = []
            for record in records:
                event_data = None
                if record.event_data:
                    try:
                        event_data = json.loads(record.event_data)
                    except (json.JSONDecodeError, TypeError):
                        event_data = None

                items.append(
                    AuditRecordResponse(
                        id=record.id,
                        user_id=record.user_id,
                        session_id=record.session_id,
                        event_type=record.event_type,
                        event_target=record.event_target,
                        page_path=record.page_path,
                        event_data=event_data,
                        client_timestamp=record.client_timestamp,
                        server_timestamp=record.server_timestamp,
                        client_ip=record.client_ip,
                    )
                )

            total_pages = math.ceil(total_count / params.page_size) if total_count > 0 else 0

            return AuditQueryResponse(
                items=items,
                total_count=total_count,
                current_page=params.page,
                total_pages=total_pages,
            )

    async def cleanup_expired_records(self, retention_days: int | None = None) -> int:
        """Delete audit records older than the retention period.

        Deletes in batches of 1000 to avoid long-running transactions.

        Args:
            retention_days: Override retention period (uses config default if None).

        Returns:
            Total number of deleted records.
        """
        if retention_days is None:
            retention_days = getattr(self._settings, "AUDIT_RETENTION_DAYS", 90)

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        total_deleted = 0
        batch_size = 1000
        start_time = time.time()

        try:
            while True:
                async with unit_of_work() as session:
                    # Find IDs to delete in this batch
                    subquery = (
                        select(AuditRecord.id)
                        .where(AuditRecord.server_timestamp < cutoff)
                        .limit(batch_size)
                    )
                    result = await session.execute(subquery)
                    ids_to_delete = [row[0] for row in result.fetchall()]

                    if not ids_to_delete:
                        break

                    stmt = delete(AuditRecord).where(AuditRecord.id.in_(ids_to_delete))
                    await session.execute(stmt)
                    total_deleted += len(ids_to_delete)

                    if len(ids_to_delete) < batch_size:
                        break

            duration = time.time() - start_time
            logger.info(
                f"Audit cleanup completed: deleted={total_deleted} "
                f"retention_days={retention_days} duration={duration:.2f}s",
            )
        except Exception as exc:
            duration = time.time() - start_time
            logger.error(
                f"Audit cleanup failed: deleted_so_far={total_deleted} "
                f"duration={duration:.2f}s error={exc}",
            )

        return total_deleted
