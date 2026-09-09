"""Recover a bounded batch of stranded Iteration 197 publication receipts.

The default is a dry run: it proves that the pending receipts still match their
immutable source, calendar, or identity entity, then rolls back.  Pass
``--apply`` only after reviewing the count.  The command makes no provider
network request.

Run from ``src/backend``:
    conda run -n base python scripts/recover_market_data_publications.py
    conda run -n base python scripts/recover_market_data_publications.py --apply --limit 100
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import async_session_maker
from app.services.market_data.publication import (
    MarketDataPublicationError,
    MarketDataPublicationManager,
)


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Publish validated pending receipts. The default only validates and rolls back.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum pending receipts to inspect in this one bounded run (1-10000).",
    )
    return parser.parse_args(argv)


async def _run(*, limit: int, apply: bool) -> dict[str, object]:
    """Run one bounded recovery batch and return a non-sensitive aggregate."""
    async with async_session_maker() as session:
        manager = MarketDataPublicationManager(session)
        publication_ids = await manager.recover_pending(limit=limit, dry_run=not apply)
    return {
        "mode": "applied" if apply else "dry_run",
        "receipt_count": len(publication_ids),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Emit one stable JSON summary suitable for operator logs and automation."""
    args = _arguments(argv)
    try:
        result = asyncio.run(_run(limit=args.limit, apply=bool(args.apply)))
    except (MarketDataPublicationError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, MarketDataPublicationError) else "PUBLICATION_RECOVERY_ARGUMENT_INVALID"
        print(json.dumps({"status": "error", "code": code}, sort_keys=True))
        return 2
    except Exception:
        # Driver exception text can carry connection details, so do not print
        # a traceback or arbitrary exception text into operator-facing JSON.
        print(json.dumps({"status": "error", "code": "PUBLICATION_RECOVERY_FAILED"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "ok", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
