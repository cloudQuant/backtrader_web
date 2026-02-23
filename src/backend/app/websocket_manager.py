"""
WebSocket real-time push service.

Used for real-time push of backtest progress and logs.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

from app.schemas.backtest_enhanced import TaskStatus

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
        self.active_connections: Dict[str, List[tuple]] = {}

    async def connect(self, websocket: WebSocket, task_id: str, client_id: str):
        """Establish a WebSocket connection.

        Args:
            websocket: WebSocket connection object.
            task_id: Task ID.
            client_id: Client ID (for multiple connections to the same task).
        """
        await websocket.accept()

        # Add to active connections
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []

        self.active_connections[task_id].append((websocket, client_id))

        # Send connection success message
        await self.send_to_task(task_id, {
            "type": "connected",
            "task_id": task_id,
            "message": "WebSocket connected successfully",
        })

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
                (ws, cid) for ws, cid in self.active_connections[task_id]
                if ws != websocket and cid != client_id
            ]

            # Delete task if no more connections
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

        logger.info(f"WebSocket disconnected: task_id={task_id}, client_id={client_id}")

    async def send_to_task(self, task_id: str, message: Dict[str, Any]):
        """Send a message to all connections for a specific task.

        Args:
            task_id: Task ID.
            message: Message to send.
        """
        if task_id not in self.active_connections:
            logger.warning(f"Task {task_id} has no active connections")
            return

        # Get all connections for the task
        connections = self.active_connections[task_id]
        dead_connections = []

        for websocket, client_id in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send message: task_id={task_id}, client_id={client_id}, {e}")
                dead_connections.append((websocket, client_id))

        # Remove dead connections
        for dead_ws, dead_cid in dead_connections:
            self.disconnect(dead_ws, task_id, dead_cid)

        logger.debug(f"Sent message to task {task_id}: {message.get('type')}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients.

        Args:
            message: Message to broadcast.
        """
        for task_id, connections in list(self.active_connections.items()):
            for websocket, client_id in connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast message: {e}")
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
        data: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.progress = progress
        self.message = message
        self.data = data or {}
        self.type = MessageType.PROGRESS

    def to_dict(self) -> Dict[str, Any]:
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
        result: Dict[str, Any],
    ):
        self.task_id = task_id
        self.result = result
        self.type = MessageType.COMPLETED if result.get('status') == TaskStatus.COMPLETED else MessageType.FAILED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation of the result message.
        """
        return {
            "type": self.type,
            "task_id": self.task_id,
            "result": self.result,
        }


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
        data: Optional[Dict[str, Any]] = None,
    ):
        self.task_id = task_id
        self.level = level  # info, warning, error
        self.message = message
        self.data = data or {}
        self.type = MessageType.LOG

    def to_dict(self) -> Dict[str, Any]:
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
