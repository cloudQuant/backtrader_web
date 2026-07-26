"""Gateway runtime/command transport helpers for the quote service.

Extracted from ``app/services/quote_service.py`` (REFACTORING_BACKLOG.md P2#13,
slice 1: "gateway/runtime discovery and the ZMQ command transport").

These are pure module-level functions — no ``QuoteService`` state. The
``QuoteService`` facade delegates to them, keeping transport concerns out of
the service body.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def send_gateway_command(
    command_endpoint: str,
    command: str,
    payload: dict[str, Any],
    send_timeout_ms: int = 3000,
    recv_timeout_ms: int = 3000,
) -> Any | None:
    """Send a single request/response command to a gateway over a ZMQ DEALER socket.

    Returns the ``data`` field of an ``{"status": "ok", "data": ...}`` reply, or
    ``None`` on timeout / transport error / non-ok reply. Never raises — all
    failures are logged and swallowed so the quote read path degrades to
    cached/empty data rather than erroring.
    """
    try:
        import zmq
    except ImportError:
        logger.warning("pyzmq not installed; cannot execute %s on %s", command, command_endpoint)
        return None
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.DEALER)
    sock.setsockopt(zmq.IDENTITY, uuid.uuid4().hex.encode("utf-8"))
    sock.setsockopt(zmq.SNDTIMEO, send_timeout_ms)
    sock.setsockopt(zmq.RCVTIMEO, recv_timeout_ms)
    try:
        sock.connect(command_endpoint)
        request = {
            "request_id": uuid.uuid4().hex,
            "command": command,
            "payload": payload,
        }
        sock.send(json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        resp_raw = sock.recv()
        resp = json.loads(resp_raw.decode("utf-8"))
        if isinstance(resp, dict) and resp.get("status") == "ok":
            return resp.get("data")
        if isinstance(resp, dict):
            logger.warning("%s failed for %s: %s", command, command_endpoint, resp.get("error"))
        else:
            logger.warning("%s returned invalid response for %s", command, command_endpoint)
    except zmq.Again:
        logger.warning("%s timed out for %s", command, command_endpoint)
    except Exception:
        logger.exception("Failed to execute %s for %s", command, command_endpoint)
    finally:
        sock.close()
    return None
