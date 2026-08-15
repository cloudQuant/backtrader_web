#!/usr/bin/env python3
"""Dry-run-first import of the approved Iteration 192 AkShare pilot manifest."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "src" / "backend"
DEFAULT_MANIFEST = REPO_ROOT / "config" / "asset_research_approved_manifest.json"


async def _import_manifest(path: Path, dry_run: bool) -> int:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app.db.database import async_session_maker
    from app.services.asset_research.importers.approved_manifest_importer import (
        ApprovedManifestImporter,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    async with async_session_maker() as db:
        report = await ApprovedManifestImporter(db).import_payload(
            payload=payload,
            dry_run=dry_run,
        )
    print(  # noqa: T201
        json.dumps(
            {
                "dry_run": report.dry_run,
                "passed": report.passed,
                "source_count": report.source_count,
                "instrument_count": report.instrument_count,
                "manifest_count": report.manifest_count,
                "errors": list(report.errors),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report.passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist rows; without this flag only a dry-run is performed",
    )
    args = parser.parse_args()
    return asyncio.run(_import_manifest(args.manifest.resolve(), dry_run=not args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
