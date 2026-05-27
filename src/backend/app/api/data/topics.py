import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from app.api.data_management_deps import require_data_admin_user
from app.api.deps import get_current_user, get_websocket_current_user
from app.services.data_topic_hub import TopicPolicy, get_shared_data_topic_hub
from app.services.ws_gateway import get_shared_ws_gateway

router = APIRouter(prefix="/data-topics", tags=["Data Topics"])


@router.get("")
async def list_topics(current_user=Depends(get_current_user)):
    items = get_shared_data_topic_hub().list_topics()
    return {"items": items, "total": len(items)}


@router.post("/register")
async def register_topic(payload: dict, current_user=Depends(get_current_user)):
    topic = str(payload["topic"])
    policy = TopicPolicy(**dict(payload.get("policy") or {}))
    get_shared_data_topic_hub().register_topic(topic, policy)
    return {"topic": topic, "policy": asdict(policy)}


@router.get("/stats")
async def topic_stats(current_user=Depends(require_data_admin_user)):
    return get_shared_data_topic_hub().stats()


@router.get("/{topic:path}/peek")
async def peek_topic(topic: str, current_user=Depends(get_current_user)):
    value = await get_shared_data_topic_hub().peek(topic)
    return {"topic": topic, "value": value}


@router.post("/{topic:path}/refresh")
async def refresh_topic(topic: str, current_user=Depends(get_current_user)):
    value = await get_shared_data_topic_hub().request(topic, force=True)
    return {"topic": topic, "value": value}


@router.post("/{topic:path}/push")
async def push_topic(topic: str, payload: dict, current_user=Depends(get_current_user)):
    delivered = await get_shared_data_topic_hub().push(topic, payload.get("value"))
    return {"topic": topic, "delivered": delivered}


def _bind_shared_topic_gateway():
    hub = get_shared_data_topic_hub()
    gateway = get_shared_ws_gateway()
    hub.set_ws_gateway(gateway)
    return hub, gateway


async def _stream_topics_websocket(websocket: WebSocket, *, topic: str | None = None, pattern: str | None = None) -> None:
    current_user, accepted_subprotocol = get_websocket_current_user(websocket)
    if current_user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    hub, gateway = _bind_shared_topic_gateway()
    client_id = f"data-topic-{id(websocket)}"
    subscribed_pattern = pattern or topic or "*"
    connected = await gateway.connect(client_id, token=current_user.sub)
    if not connected:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept(subprotocol=accepted_subprotocol)
    await gateway.subscribe(client_id, [subscribed_pattern])
    await websocket.send_json({"type": "connected", "topic": topic, "pattern": pattern})

    if topic is not None:
        initial_value = await hub.peek(topic)
        if initial_value is not None:
            await websocket.send_json({"type": "snapshot", "topic": topic, "value": initial_value})

    try:
        while True:
            pending = gateway.pop_messages(client_id)
            for matched_topic, payload in pending:
                await websocket.send_json({"type": "topic_update", "topic": matched_topic, "value": payload})

            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            if data == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if data == "refresh" and topic is not None:
                value = await hub.request(topic, force=True)
                await websocket.send_json({"type": "snapshot", "topic": topic, "value": value})
    except WebSocketDisconnect:
        pass
    finally:
        gateway.disconnect(client_id)


async def websocket_topic_endpoint(websocket: WebSocket, topic: str) -> None:
    await _stream_topics_websocket(websocket, topic=topic)


async def websocket_pattern_endpoint(websocket: WebSocket) -> None:
    pattern = websocket.query_params.get("pattern") or "*"
    await _stream_topics_websocket(websocket, pattern=pattern)
