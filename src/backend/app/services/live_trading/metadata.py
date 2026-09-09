"""Helpers for live trading instance metadata normalization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Private keys are persisted by the execution service, never accepted from
# ``LiveInstanceCreate``.  They form the server-owned launch epoch used by
# AI-research paper promotion; public display timestamps remain legacy-local.
SERVER_RUNTIME_LAUNCH_ID_FIELD = "_server_runtime_launch_id"
SERVER_RUNTIME_LAUNCH_STARTED_AT_FIELD = "_server_runtime_launch_started_at"


def instance_timestamp() -> str:
    """Return the local timestamp format used by persisted live instances."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def server_runtime_launch_timestamp() -> str:
    """Return an unambiguous UTC timestamp for a newly spawned process."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def clear_server_runtime_launch_observation(instance: dict[str, Any]) -> bool:
    """Invalidate a private paper-review epoch after lifecycle uncertainty.

    A PID recovered by a later scan is not proof that it is the server-issued
    process that supplied an earlier review. Terminal state and reattachment
    paths clear this pair; only a successful local spawn may publish a new
    UUID/timestamp pair.
    """
    changed = False
    for field in (
        SERVER_RUNTIME_LAUNCH_ID_FIELD,
        SERVER_RUNTIME_LAUNCH_STARTED_AT_FIELD,
    ):
        if field in instance:
            instance.pop(field, None)
            changed = True
    return changed


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def infer_gateway_type(instance: dict[str, Any]) -> str:
    """Infer a stable top-level gateway type from instance metadata."""
    explicit = _clean_text(instance.get("gateway_type"))
    if explicit:
        return explicit

    params = instance.get("params")
    if not isinstance(params, dict):
        return ""
    gateway = params.get("gateway")
    if not isinstance(gateway, dict):
        return ""

    for key in ("provider", "gateway_type", "exchange_type", "type"):
        value = _clean_text(gateway.get(key))
        if value:
            return value
    return ""


def normalize_instance_metadata(
    instance: dict[str, Any],
    *,
    instance_id: str | None = None,
    now: str | None = None,
    touch: bool = False,
) -> bool:
    """Backfill and optionally update persisted instance metadata.

    Returns True when ``instance`` was modified.
    """
    changed = False

    if instance_id and not _clean_text(instance.get("id")):
        instance["id"] = instance_id
        changed = True

    gateway_type = infer_gateway_type(instance)
    if _clean_text(instance.get("gateway_type")) != gateway_type:
        instance["gateway_type"] = gateway_type
        changed = True
    elif "gateway_type" not in instance:
        instance["gateway_type"] = gateway_type
        changed = True

    timestamp = now or instance_timestamp()
    if touch:
        if instance.get("updated_at") != timestamp:
            instance["updated_at"] = timestamp
            changed = True
    elif not _clean_text(instance.get("updated_at")):
        instance["updated_at"] = _clean_text(instance.get("created_at")) or timestamp
        changed = True

    return changed
