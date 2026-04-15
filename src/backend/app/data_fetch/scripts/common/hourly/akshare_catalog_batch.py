from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.data_fetch.scripts.common.daily.akshare_catalog_endpoint import run_endpoint
from app.utils.akshare_catalog_utils import (
    default_batch_index_utc,
    make_akcat_table_name,
    select_endpoint_batch,
)

logger = logging.getLogger(__name__)


def _load_endpoints_flat() -> dict[str, Any]:
    backend_dir = Path(__file__).resolve().parents[5]  # .../backend
    repo_root = backend_dir.parent
    path = repo_root / "docs" / "akshare_catalog" / "endpoints_flat.json"
    return json.loads(path.read_text(encoding="utf-8"))


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
    catalog = _load_endpoints_flat()
    all_endpoints = sorted(catalog.keys())

    if endpoint_names:
        selected = list(endpoint_names)
    else:
        selected = select_endpoint_batch(all_endpoints, batch_size=int(batch_size), batch_index=idx)

    stats = {"selected": len(selected), "ok": 0, "failed": 0, "rows": 0}
    failures: list[dict[str, Any]] = []

    for ep in selected:
        try:
            res = run_endpoint(
                endpoint_name=ep,
                target_table=make_akcat_table_name(ep),
                args=[],
                kwargs={},
                call_timeout=call_timeout,
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
