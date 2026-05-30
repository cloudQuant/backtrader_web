import asyncio
import fnmatch
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class TopicPolicy:
    ttl_ms: int = 1000
    min_interval_ms: int = 0
    refresh_timeout_ms: int = 1000
    push_only: bool = False
    coalesce_within_ms: int = 0
    drop_on_idle: bool = False
    pause_when_inactive: bool = False


class Producer:
    def topic_patterns(self) -> list[str]:
        return []

    async def refresh(self, topics: list[str]) -> dict[str, Any]:
        return {}

    def max_requests_per_sec(self) -> float:
        return 1.0


@dataclass(slots=True)
class _TopicState:
    policy: TopicPolicy
    value: Any = None
    updated_at: float = 0.0
    last_refresh_at: float = 0.0


@dataclass(slots=True)
class _Subscription:
    owner: str
    pattern: str
    callback: Callable[[str, Any], Any]


class DataTopicHub:
    def __init__(self) -> None:
        self._topics: dict[str, _TopicState] = {}
        self._producers: list[Producer] = []
        self._subscriptions: dict[str, _Subscription] = {}
        self._error_subscribers: list[Callable[[dict[str, Any]], Any]] = []
        self._coalesce_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._coalesce_values: dict[tuple[str, str], Any] = {}
        self._topic_errors: dict[str, dict[str, Any]] = {}
        self._error_count = 0
        self._ws_gateway: Any | None = None

    def register_topic(self, topic: str, policy: TopicPolicy | None = None) -> None:
        current = self._topics.get(topic)
        if current is None:
            self._topics[topic] = _TopicState(policy=policy or TopicPolicy())
        elif policy is not None:
            current.policy = policy

    def register_producer(self, producer: Producer) -> None:
        self._producers.append(producer)

    def set_ws_gateway(self, ws_gateway: Any) -> None:
        self._ws_gateway = ws_gateway

    def list_topics(self) -> list[dict[str, Any]]:
        return [
            {
                "topic": topic,
                "has_value": state.value is not None,
                "updated_at_ms": int(state.updated_at * 1000) if state.updated_at else None,
                "policy": asdict(state.policy),
                "subscription_count": self._subscription_count_for_topic(topic),
                "last_error": self._topic_errors.get(topic),
            }
            for topic, state in sorted(self._topics.items())
        ]

    def stats(self) -> dict[str, Any]:
        ws_metrics = None
        if self._ws_gateway is not None:
            ws_metrics = asdict(self._ws_gateway.metrics())
        return {
            "total_topics": len(self._topics),
            "topics_with_value": sum(
                1 for state in self._topics.values() if state.value is not None
            ),
            "subscription_count": len(self._subscriptions),
            "error_count": self._error_count,
            "ws_gateway": ws_metrics,
        }

    def peek_raw(self, topic: str) -> Any:
        state = self._topics.get(topic)
        return None if state is None else state.value

    async def peek(self, topic: str) -> Any:
        return await self.request(topic, force=False)

    async def request(self, topic: str, *, force: bool = False) -> Any:
        state = self._topics.setdefault(topic, _TopicState(policy=TopicPolicy()))
        if state.policy.push_only:
            return state.value
        now = time.monotonic()
        fresh = state.value is not None and (now - state.updated_at) * 1000 <= state.policy.ttl_ms
        if fresh and not force:
            return state.value
        if state.policy.min_interval_ms > 0:
            elapsed_ms = (now - state.last_refresh_at) * 1000
            if elapsed_ms < state.policy.min_interval_ms and state.value is not None:
                return state.value
        producer = self._find_producer(topic)
        if producer is None:
            return state.value
        state.last_refresh_at = now
        try:
            values = await asyncio.wait_for(
                producer.refresh([topic]),
                timeout=max(state.policy.refresh_timeout_ms, 1) / 1000,
            )
        except TimeoutError:
            self._emit_error({"topic": topic, "code": "refresh_timeout"})
            return state.value
        except Exception as exc:
            self._emit_error({"topic": topic, "code": "refresh_failed", "message": str(exc)})
            return state.value
        if topic in values:
            await self.push(topic, values[topic])
        return self.peek_raw(topic)

    def subscribe(self, owner: str, pattern: str, callback: Callable[[str, Any], Any]) -> str:
        subscription_id = str(uuid.uuid4())
        self._subscriptions[subscription_id] = _Subscription(
            owner=owner, pattern=pattern, callback=callback
        )
        return subscription_id

    def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)

    def subscribe_errors(self, callback: Callable[[dict[str, Any]], Any]) -> None:
        self._error_subscribers.append(callback)

    async def push(self, topic: str, value: Any) -> int:
        state = self._topics.setdefault(topic, _TopicState(policy=TopicPolicy()))
        state.value = value
        state.updated_at = time.monotonic()
        self._topic_errors.pop(topic, None)
        matching = [
            (subscription_id, subscription)
            for subscription_id, subscription in self._subscriptions.items()
            if fnmatch.fnmatch(topic, subscription.pattern)
        ]
        for subscription_id, subscription in matching:
            if state.policy.coalesce_within_ms > 0:
                self._schedule_coalesced(
                    subscription_id, subscription, topic, value, state.policy.coalesce_within_ms
                )
            else:
                await self._deliver(subscription.callback, topic, value)
        delivered = len(matching)
        if self._ws_gateway is not None:
            delivered += await self._ws_gateway.publish(topic, value)
        return delivered

    def retire_topic(self, topic: str) -> None:
        self._topics.pop(topic, None)

    def _find_producer(self, topic: str) -> Producer | None:
        for producer in self._producers:
            if any(fnmatch.fnmatch(topic, pattern) for pattern in producer.topic_patterns()):
                return producer
        return None

    def _schedule_coalesced(
        self,
        subscription_id: str,
        subscription: _Subscription,
        topic: str,
        value: Any,
        delay_ms: int,
    ) -> None:
        key = (subscription_id, topic)
        self._coalesce_values[key] = value
        task = self._coalesce_tasks.get(key)
        if task is None or task.done():
            self._coalesce_tasks[key] = asyncio.create_task(
                self._deliver_coalesced(key, subscription.callback, topic, delay_ms)
            )

    async def _deliver_coalesced(
        self,
        key: tuple[str, str],
        callback: Callable[[str, Any], Any],
        topic: str,
        delay_ms: int,
    ) -> None:
        await asyncio.sleep(delay_ms / 1000)
        value = self._coalesce_values.pop(key, None)
        self._coalesce_tasks.pop(key, None)
        await self._deliver(callback, topic, value)

    async def _deliver(self, callback: Callable[[str, Any], Any], topic: str, value: Any) -> None:
        result = callback(topic, value)
        if isinstance(result, Awaitable):
            await result

    def _emit_error(self, error: dict[str, Any]) -> None:
        topic = str(error.get("topic") or "")
        if topic:
            self._topic_errors[topic] = dict(error)
        self._error_count += 1
        for callback in self._error_subscribers:
            callback(error)

    def _subscription_count_for_topic(self, topic: str) -> int:
        return sum(
            1
            for subscription in self._subscriptions.values()
            if fnmatch.fnmatch(topic, subscription.pattern)
        )


_shared_hub = DataTopicHub()


def get_shared_data_topic_hub() -> DataTopicHub:
    return _shared_hub
