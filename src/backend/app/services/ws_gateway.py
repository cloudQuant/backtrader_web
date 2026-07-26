from __future__ import annotations

import fnmatch
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class WSGatewayMetrics:
    connection_count: int
    subscription_count: int


class WSGateway:
    def __init__(
        self, *, token_validator: Callable[[str], bool], heartbeat_timeout_ms: int = 30_000
    ) -> None:
        self.token_validator = token_validator
        self.heartbeat_timeout_ms = heartbeat_timeout_ms
        self._connections: dict[str, float] = {}
        self._subscriptions: dict[str, list[str]] = {}
        self._messages: list[tuple[str, str, Any]] = []

    async def connect(self, client_id: str, *, token: str) -> bool:
        if not self.token_validator(token):
            return False
        self._connections[client_id] = time.monotonic()
        self._subscriptions.setdefault(client_id, [])
        return True

    async def subscribe(self, client_id: str, patterns: list[str]) -> None:
        self._subscriptions.setdefault(client_id, [])
        self._subscriptions[client_id].extend(patterns)
        self.touch(client_id)

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        self._subscriptions.pop(client_id, None)
        self._messages = [item for item in self._messages if item[0] != client_id]

    async def publish(self, topic: str, payload: Any) -> int:
        delivered = 0
        for client_id, patterns in self._subscriptions.items():
            if any(fnmatch.fnmatch(topic, pattern) for pattern in patterns):
                self._messages.append((client_id, topic, payload))
                delivered += 1
                self.touch(client_id)
        return delivered

    def pop_messages(self, client_id: str) -> list[tuple[str, Any]]:
        matched: list[tuple[str, Any]] = []
        remaining: list[tuple[str, str, Any]] = []
        for current_client_id, topic, payload in self._messages:
            if current_client_id == client_id:
                matched.append((topic, payload))
            else:
                remaining.append((current_client_id, topic, payload))
        self._messages = remaining
        return matched

    def touch(self, client_id: str) -> None:
        if client_id in self._connections:
            self._connections[client_id] = time.monotonic()

    def close_idle_connections(self) -> list[str]:
        now = time.monotonic()
        closed: list[str] = []
        for client_id, last_seen in list(self._connections.items()):
            if (now - last_seen) * 1000 > self.heartbeat_timeout_ms:
                closed.append(client_id)
                self._connections.pop(client_id, None)
                self._subscriptions.pop(client_id, None)
        return closed

    def metrics(self) -> WSGatewayMetrics:
        return WSGatewayMetrics(
            connection_count=len(self._connections),
            subscription_count=sum(len(items) for items in self._subscriptions.values()),
        )


_shared_gateway = WSGateway(token_validator=lambda token: bool(token))


def get_shared_ws_gateway() -> WSGateway:
    return _shared_gateway
