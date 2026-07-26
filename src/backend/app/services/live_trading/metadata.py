"""Helpers for live trading instance metadata normalization."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def instance_timestamp() -> str:
    """Return the local timestamp format used by persisted live instances."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
