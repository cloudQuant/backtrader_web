"""Import a reviewed Iteration 197 calendar manifest without network access.

The default executes the full validation and write path, then rolls back.
Use --apply only after reviewing the structured dry-run result.

Run from src/backend:
    conda run -n base python scripts/import_market_data_calendar.py calendar.json
    conda run -n base python scripts/import_market_data_calendar.py --apply calendar.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import async_session_maker
from app.services.market_data.calendar_importer import (
    MarketDataCalendarImporter,
    MarketDataCalendarImportError,
    load_market_data_calendar_manifest,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Path to a reviewed calendar JSON manifest")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the complete import. The default performs a rollback dry-run.",
    )
    return parser.parse_args()


async def _run(*, manifest_path: Path, apply: bool) -> dict[str, object]:
    payload = load_market_data_calendar_manifest(manifest_path)
    async with async_session_maker() as session:
        try:
            result = await MarketDataCalendarImporter(session).import_payload(
                payload=payload,
                dry_run=not apply,
            )
            if apply:
                await session.commit()
                mode = "applied"
            else:
                await session.rollback()
                mode = "dry_run"
        except Exception:
            await session.rollback()
            raise
    return {"mode": mode, **result.as_dict()}


def main() -> int:
    """Run the operator-only calendar import and print safe JSON output."""
    args = _arguments()
    try:
        output = asyncio.run(_run(manifest_path=args.manifest, apply=bool(args.apply)))
    except MarketDataCalendarImportError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"status": "error", "code": "CALENDAR_IMPORT_FAILED"}))
        return 1
    print(json.dumps({"status": "ok", **output}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
