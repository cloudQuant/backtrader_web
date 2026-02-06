"""
WebSocket 实时推送服务

用于回测进度和日志的实时推送
"""
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

from app.schemas.backtest_enhanced import TaskStatus

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # 任务 ID 到 WebSocket 连接列表的映射
        # key: task_id, value: list of (websocket, client_id)
        self.active_connections: Dict[str, List[tuple]] = {}

    async def connect(self, websocket: WebSocket, task_id: str, client_id: str):
        """
        建立连接

        Args:
            websocket: WebSocket 连接对象
            task_id: 任务 ID
            client_id: 客户端 ID（用于同一任务的多个连接）
        """
        await websocket.accept()

        # 添加到活跃连接
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []

        self.active_connections[task_id].append((websocket, client_id))

        # 发送连接成功消息
        await self.send_to_task(task_id, {
            "type": "connected",
            "task_id": task_id,
            "message": "WebSocket 连接成功",
        })

        logger.info(f"WebSocket 连接建立: task_id={task_id}, client_id={client_id}")

    def disconnect(self, websocket: WebSocket, task_id: str, client_id: str):
        """
        断开连接

        Args:
            websocket: WebSocket 连接对象
            task_id: 任务 ID
            client_id: 客户端 ID
        """
        if task_id in self.active_connections:
            # 移除指定客户端的连接
            self.active_connections[task_id] = [
                (ws, cid) for ws, cid in self.active_connections[task_id]
                if ws != websocket and cid != client_id
            ]

            # 如果没有连接了，删除任务
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

        logger.info(f"WebSocket 连接断开: task_id={task_id}, client_id={client_id}")

    async def send_to_task(self, task_id: str, message: Dict[str, Any]):
        """
        向特定任务的所有连接发送消息

        Args:
            task_id: 任务 ID
            message: 要发送的消息
        """
        if task_id not in self.active_connections:
            logger.warning(f"任务 {task_id} 没有活跃连接")
            return

        # 获取该任务的所有连接
        connections = self.active_connections[task_id]
        dead_connections = []

        for websocket, client_id in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"发送消息失败: task_id={task_id}, client_id={client_id}, {e}")
                dead_connections.append((websocket, client_id))

        # 移除死亡的连接
        for dead_ws, dead_cid in dead_connections:
            self.disconnect(dead_ws, task_id, dead_cid)

        logger.debug(f"向任务 {task_id} 发送消息: {message.get('type')}")

    async def broadcast(self, message: Dict[str, Any]):
        """
        广播消息给所有连接

        Args:
            message: 要广播的消息
        """
        for task_id, connections in list(self.active_connections.items()):
            for websocket, client_id in connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"广播消息失败: {e}")
                    self.disconnect(websocket, task_id, client_id)

    def get_connection_count(self, task_id: str) -> int:
        """
        获取任务的连接数

        Args:
            task_id: 任务 ID

        Returns:
            int: 连接数
        """
        return len(self.active_connections.get(task_id, []))

    def get_total_connections(self) -> int:
        """
        获取总连接数

        Returns:
            int: 总连接数
        """
        return sum(len(conns) for conns in self.active_connections.values())


# 全局连接管理器实例
manager = ConnectionManager()


# 消息类型常量
class MessageType:
    """WebSocket 消息类型"""
    CONNECTED = "connected"
    PROGRESS = "progress"
    LOG = "log"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProgressMessage:
    """进度消息"""

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
        """转换为字典"""
        return {
            "type": self.type,
            "task_id": self.task_id,
            "progress": self.progress,
            "message": self.message,
            "data": self.data,
        }


class ResultMessage:
    """回测结果消息"""

    def __init__(
        self,
        task_id: str,
        result: Dict[str, Any],
    ):
        self.task_id = task_id
        self.result = result
        self.type = MessageType.COMPLETED if result.get('status') == TaskStatus.COMPLETED else MessageType.FAILED

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "type": self.type,
            "task_id": self.task_id,
            "result": self.result,
        }


class LogMessage:
    """日志消息"""

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
        """转换为字典"""
        return {
            "type": self.type,
            "task_id": self.task_id,
            "level": self.level,
            "message": self.message,
            "data": self.data,
        }
