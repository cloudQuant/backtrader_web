"""
WebSocket real-time push service.

Used for real-time push of backtest progress and logs.
"""

import logging
from typing import Any

from fastapi import WebSocket

from app.schemas.backtest_enhanced import BacktestConnectedEvent, TaskStatus

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager.

    Attributes:
        active_connections: Dictionary mapping task IDs to WebSocket connection lists.
            key: task_id, value: list of (websocket, client_id) tuples.
    """

    def __init__(self):
        # Task ID to WebSocket connection list mapping
        # key: task_id, value: list of (websocket, client_id)
        self.active_connections: dict[str, list[tuple]] = {}
        # Track connections known to be closed to avoid sending to dead sockets
        self._closed_connections: set[WebSocket] = set()

    async def send_to_connection(self, websocket: WebSocket, message: dict[str, Any]) -> bool:
        """Send a message to a single WebSocket connection.

        Returns True on success, False if the connection is dead or send failed.
        """
        if websocket in self._closed_connections:
            return False
        try:
            await websocket.send_json(message)
            return True
        except Exception:
            logger.exception("Failed to send message to a WebSocket connection")
            self._closed_connections.add(websocket)
            return False

    async def connect(
        self,
        websocket: WebSocket,
        task_id: str,
        client_id: str,
        subprotocol: str | None = None,
    ):
        """Establish a WebSocket connection.

        Args:
            websocket: WebSocket connection object.
            task_id: Task ID.
            client_id: Client ID (for multiple connections to the same task).
        """
        if subprotocol is None:
            await websocket.accept()
        else:
            await websocket.accept(subprotocol=subprotocol)

        # Add to active connections
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []

        self.active_connections[task_id].append((websocket, client_id))

        await self.send_to_connection(
            websocket,
            BacktestConnectedEvent(task_id=task_id, client_id=client_id).model_dump(mode="python"),
        )

        logger.info(f"WebSocket connected: task_id={task_id}, client_id={client_id}")

    def disconnect(self, websocket: WebSocket, task_id: str, client_id: str):
        """Disconnect a WebSocket connection.

        Args:
            websocket: WebSocket connection object.
            task_id: Task ID.
            client_id: Client ID.
        """
        if task_id in self.active_connections:
            # Remove specified client connection
            self.active_connections[task_id] = [
                (ws, cid)
                for ws, cid in self.active_connections[task_id]
                if not (ws == websocket and cid == client_id)
            ]

            # Delete task if no more connections
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

        self._closed_connections.discard(websocket)
        logger.info(f"WebSocket disconnected: task_id={task_id}, client_id={client_id}")

    async def send_to_task(self, task_id: str, message: dict[str, Any]):
        """Send a message to all connections for a specific task.

        Args:
            task_id: Task ID.
            message: Message to send.
        """
        if task_id not in self.active_connections:
            logger.warning(f"Task {task_id} has no active connections")
            return

        # Get all connections for the task
        connections = list(self.active_connections[task_id])
        dead_connections = []

        for websocket, client_id in connections:
            sent = await self.send_to_connection(websocket, message)
            if not sent:
                dead_connections.append((websocket, client_id))

        # Remove dead connections
        for dead_ws, dead_cid in dead_connections:
            self.disconnect(dead_ws, task_id, dead_cid)

        logger.debug(f"Sent message to task {task_id}: {message.get('type')}")

    async def broadcast(self, message: dict[str, Any]):
        """Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast.
        """
        for task_id, connections in list(self.active_connections.items()):
            for websocket, client_id in connections:
                sent = await self.send_to_connection(websocket, message)
                if not sent:
                    self.disconnect(websocket, task_id, client_id)

    def get_connection_count(self, task_id: str) -> int:
        """Get the number of connections for a task.

        Args:
            task_id: Task ID.

        Returns:
            The number of connections.
        """
        return len(self.active_connections.get(task_id, []))

    def get_total_connections(self) -> int:
        """Get the total number of active connections.

        Returns:
            The total number of connections across all tasks.
        """
        return sum(len(conns) for conns in self.active_connections.values())


# Global connection manager instance
manager = ConnectionManager()


# Message type constants
class MessageType:
    """WebSocket message types."""

    CONNECTED = "connected"
    PROGRESS = "progress"
    LOG = "log"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ERROR = "error"


class ProgressMessage:
    """Progress message class.

    Attributes:
        task_id: Task ID.
        progress: Progress percentage (0-100).
        message: Optional status message.
        data: Optional data payload.
        type: Message type (always "progress").
    """

    def __init__(
        self,
        task_id: str,
        progress: int,
        message: str = "",
        data: dict[str, Any] | None = None,
    ):
        self.task_id = task_id
        self.progress = progress
        self.message = message
        self.data = data or {}
        self.type = MessageType.PROGRESS

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the progress message.
        """
        return {
            "type": self.type,
            "task_id": self.task_id,
            "progress": self.progress,
            "message": self.message,
            "data": self.data,
        }


class ResultMessage:
    """Backtest result message class.

    Attributes:
        task_id: Task ID.
        result: Result dictionary.
        type: Message type (completed or failed).
    """

    def __init__(
        self,
        task_id: str,
        result: dict[str, Any],
    ):
        self.task_id = task_id
        self.result = result
        self.type = (
            MessageType.COMPLETED
            if result.get("status") == TaskStatus.COMPLETED
            else MessageType.FAILED
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the result message.
        """
        return {
            "type": self.type,
            "task_id": self.task_id,
            "result": self.result,
        }


class ErrorMessage:
    """Standardized WebSocket error message.

    Attributes:
        task_id: Task ID (may be empty for connection-level errors).
        code: Machine-readable error code.
        message: Human-readable error description.
        type: Message type (always "error").
    """

    def __init__(
        self,
        code: str,
        message: str,
        task_id: str = "",
        data: dict[str, Any] | None = None,
    ):
        self.task_id = task_id
        self.code = code
        self.message = message
        self.data = data or {}
        self.type = MessageType.ERROR

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the error message.
        """
        result: dict[str, Any] = {
            "type": self.type,
            "code": self.code,
            "message": self.message,
        }
        if self.task_id:
            result["task_id"] = self.task_id
        if self.data:
            result["data"] = self.data
        return result


class LogMessage:
    """Log message class.

    Attributes:
        task_id: Task ID.
        level: Log level (info, warning, error).
        message: Log message content.
        data: Optional data payload.
        type: Message type (always "log").
    """

    def __init__(
        self,
        task_id: str,
        level: str,
        message: str,
        data: dict[str, Any] | None = None,
    ):
        self.task_id = task_id
        self.level = level  # info, warning, error
        self.message = message
        self.data = data or {}
        self.type = MessageType.LOG

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the log message.
        """
        return {
            "type": self.type,
            "task_id": self.task_id,
            "level": self.level,
            "message": self.message,
            "data": self.data,
        }
