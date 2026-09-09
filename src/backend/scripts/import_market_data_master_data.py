"""Import a reviewed Iteration 197 master-data JSON manifest.

The command is operator-only.  Its default dry-run executes the normal
identity persistence and lookup-key materialization path, then rolls back the
entire transaction.  Pass ``--apply`` only after reviewing the JSON summary.
No network request is made.

Run from ``src/backend``:
    conda run -n base python scripts/import_market_data_master_data.py manifest.json
    conda run -n base python scripts/import_market_data_master_data.py --apply manifest.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import async_session_maker
from app.services.market_data.master_data_importer import (
    MarketDataMasterDataImporter,
    MarketDataMasterDataImportError,
    load_market_data_master_manifest,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to a reviewed JSON identity manifest")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the complete import. The default performs a rollback dry-run.",
    )
    return parser.parse_args()


async def _run(*, manifest_path: Path, apply: bool) -> dict[str, object]:
    manifest, manifest_sha256 = load_market_data_master_manifest(manifest_path)
    async with async_session_maker() as session:
        try:
            importer = MarketDataMasterDataImporter(session)
            result = await importer.import_manifest(
                manifest,
                manifest_sha256=manifest_sha256,
            )
            if apply:
                await session.commit()
                # The first commit makes immutable identities durable. A
                # second transaction records their visibility time, so strict
                # point-in-time queries cannot see pre-commit authority facts.
                await importer.publish_staged()
                mode = "applied"
            else:
                await session.rollback()
                mode = "dry_run"
        except Exception:
            await session.rollback()
            raise
    return {"mode": mode, **result.as_dict()}


def main() -> int:
    """Run the transactional import and emit a non-secret structured summary."""
    args = _arguments()
    try:
        result = asyncio.run(_run(manifest_path=args.manifest, apply=bool(args.apply)))
    except MarketDataMasterDataImportError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, sort_keys=True))
        return 2
    except Exception:
        # Driver errors can contain a database URL, so do not write a traceback
        # or exception text into the operator-facing JSON stream.
        print(json.dumps({"status": "error", "code": "MASTER_DATA_IMPORT_FAILED"}))
        return 1
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
