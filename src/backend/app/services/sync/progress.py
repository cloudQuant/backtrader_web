"""Progress / status / history helpers for the MySQL sync service.

These are the small, side-effect-light pieces of ``SyncService`` that report
*about* a sync run rather than perform one: timestamp + byte formatting, host
normalization, and JSON history persistence. They are split out (P1#5 slice 1)
so the status surface can be unit-tested without standing up a transport.

``SyncService`` keeps thin facade methods delegating here (same pattern as
``transport.py`` and ``schema_diff.py``). The async history *locking* stays on
the service because it owns the ``asyncio.Lock``; only the file read/write
mechanics move here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

HISTORY_MAX_ENTRIES = 200


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def normalize_host(value: str) -> str:
    """Strip whitespace and reduce a URL to its bare hostname."""
    host = str(value or "").strip()
    if not host:
        return ""
    if host.startswith("http://") or host.startswith("https://"):
        parsed = urlparse(host)
        return parsed.hostname or host
    return host


def format_bytes(value: int) -> str:
    """Human-readable byte size (B/KB/MB/GB/TB)."""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(max(value, 0))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(value)} B"


def load_history(history_file: Path) -> list[dict[str, Any]]:
    """Read the on-disk sync history, tolerating missing/corrupt files."""
    if not history_file.is_file():
        return []
    try:
        payload = json.loads(history_file.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def write_history(history_file: Path, items: list[dict[str, Any]]) -> None:
    """Persist the sync history, capping at ``HISTORY_MAX_ENTRIES`` entries."""
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        json.dumps(items[:HISTORY_MAX_ENTRIES], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
