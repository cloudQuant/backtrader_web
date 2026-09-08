"""Static, fail-closed configuration for protocol-v2 dataset object resolvers."""

from __future__ import annotations

from typing import Any

from app.services.research.dataset_integrity import DatasetObjectResolver
from app.services.research.filesystem_dataset_resolver import FilesystemDatasetObjectResolver


def resolve_configured_dataset_object_resolver(settings: Any) -> DatasetObjectResolver | None:
    """Build the one reviewed resolver selected by deployment configuration.

    An empty setting intentionally means no resolver, leaving browser-initiated
    dataset registration fail-closed.  The type is an exact static allowlist,
    not an import path or a value controlled by any API request.
    """

    resolver_type = getattr(
        settings,
        "AI_RESEARCH_PROTOCOL_V2_DATASET_OBJECT_RESOLVER_TYPE",
        "",
    )
    if resolver_type in (None, ""):
        return None
    if resolver_type != "filesystem":
        raise ValueError("DATASET_OBJECT_RESOLVER_TYPE_DENIED")
    try:
        return FilesystemDatasetObjectResolver(
            object_root=_required_string(
                settings,
                "AI_RESEARCH_PROTOCOL_V2_DATASET_FILESYSTEM_ROOT",
            ),
            receipt_store=_required_string(
                settings,
                "AI_RESEARCH_PROTOCOL_V2_DATASET_RECEIPT_STORE",
            ),
            max_object_bytes=_required_int(
                settings,
                "AI_RESEARCH_PROTOCOL_V2_DATASET_MAX_BYTES",
            ),
        )
    except (OSError, TypeError, ValueError):
        raise ValueError("DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID") from None


def _required_string(settings: Any, name: str) -> str:
    """Extract a nonblank deployment string without coercing arbitrary configuration."""

    value = getattr(settings, name, None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing resolver setting")
    return value


def _required_int(settings: Any, name: str) -> int:
    """Extract an exact integer rather than accepting bools or textual coercion."""

    value = getattr(settings, name, None)
    if type(value) is not int:
        raise ValueError("invalid resolver setting")
    return value
