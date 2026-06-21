from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.data_fetch.scripts.common.daily.akshare_catalog_endpoint import run_endpoint
from app.utils.akshare_catalog_utils import (
    default_batch_index_utc,
    make_akcat_table_name,
    select_endpoint_batch,
)

logger = logging.getLogger(__name__)


def _catalog_path_candidates() -> list[Path]:
    backend_dir = Path(__file__).resolve().parents[5]  # .../backend
    repo_root = backend_dir.parent.parent
    return [
        repo_root / "docs" / "akshare_catalog" / "endpoints_flat.json",
        backend_dir.parent / "docs" / "akshare_catalog" / "endpoints_flat.json",
    ]


def _load_catalog_file() -> dict[str, Any] | None:
    for path in _catalog_path_candidates():
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _load_installed_akshare_catalog() -> dict[str, Any]:
    import akshare as ak

    return {
        name: {}
        for name in dir(ak)
        if not name.startswith("_") and callable(getattr(ak, name, None))
    }


def _load_endpoints_flat() -> dict[str, Any]:
    catalog, _source = _load_endpoint_catalog()
    return catalog


def _load_endpoint_catalog() -> tuple[dict[str, Any], str]:
    catalog = _load_catalog_file()
    if catalog is not None:
        return catalog, "file"

    catalog = _load_installed_akshare_catalog()
    if catalog:
        return catalog, "installed"

    searched = ", ".join(str(path) for path in _catalog_path_candidates())
    raise FileNotFoundError(f"No akshare catalog endpoints found. Searched: {searched}")


def _default_catalog_call_timeout() -> int:
    try:
        return int(os.getenv("AKSHARE_CATALOG_CALL_TIMEOUT", "8"))
    except ValueError:
        return 8


def _fallback_batch_size(batch_size: int) -> int:
    try:
        fallback_limit = int(os.getenv("AKSHARE_CATALOG_FALLBACK_BATCH_SIZE", "3"))
    except ValueError:
        fallback_limit = 3
    return min(batch_size, max(fallback_limit, 1))


def run(
    batch_size: int = 30,
    batch_index: int | None = None,
    endpoint_names: list[str] | None = None,
    call_timeout: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Batch downloader for `docs/akshare_catalog`.

    - If `endpoint_names` is provided, only those endpoints will run.
    - Otherwise selects a rotating batch by UTC day index.
    """
    idx = int(batch_index) if batch_index is not None else default_batch_index_utc()
    catalog, catalog_source = _load_endpoint_catalog()
    all_endpoints = sorted(catalog.keys())
    effective_batch_size = int(batch_size)
    if catalog_source == "installed":
        effective_batch_size = _fallback_batch_size(effective_batch_size)
    effective_call_timeout = (
        int(call_timeout) if call_timeout is not None else _default_catalog_call_timeout()
    )

    if endpoint_names:
        selected = list(endpoint_names)
    else:
        selected = select_endpoint_batch(
            all_endpoints, batch_size=effective_batch_size, batch_index=idx
        )

    stats = {
        "selected": len(selected),
        "ok": 0,
        "failed": 0,
        "rows": 0,
        "catalog_source": catalog_source,
        "call_timeout": effective_call_timeout,
    }
    failures: list[dict[str, Any]] = []

    for ep in selected:
        try:
            res = run_endpoint(
                endpoint_name=ep,
                target_table=make_akcat_table_name(ep),
                args=[],
                kwargs={},
                call_timeout=effective_call_timeout,
                dry_run=dry_run,
            )
            if res.get("success"):
                stats["ok"] += 1
                stats["rows"] += int(res.get("rows") or 0)
            else:
                stats["failed"] += 1
                failures.append({"endpoint": ep, "error": res})
        except Exception as e:
            stats["failed"] += 1
            failures.append({"endpoint": ep, "error": str(e)})

    return {"success": stats["failed"] == 0, "stats": stats, "failures": failures[:20]}
