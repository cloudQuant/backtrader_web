"""Backfill bounded exact market-data lookup keys from authoritative identities.

Run this only after the Iteration 197 Alembic revisions have been applied.
The script does not fetch market data, normalize symbols, or repair malformed
identity rows: it stops on integrity errors so an operator can correct the
authority before enabling triple-selector traffic. It performs a rollback-only
dry run by default; only ``--apply`` can commit a projection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Support the documented ``python scripts/...`` operational entrypoint without
# requiring an editable package install in a recovery environment.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.database import async_session_maker
from app.services.market_data.master_data import MarketDataLookupKeyMaterializer


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--after-id", default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Commit synchronized lookup keys. The default performs the same work then rolls back.",
    )
    # Retain the old flag for operator scripts while making the safe behavior
    # the default. It is intentionally a no-op alias rather than an implicit
    # opt-in to a persistent mutation.
    mode.add_argument(
        "--dry-run",
        dest="apply",
        action="store_false",
        help="Validate and report without committing (the default).",
    )
    parser.set_defaults(apply=False)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    if args.max_batches < 1:
        raise ValueError("--max-batches must be at least 1")
    cursor = args.after_id
    totals = {"processed": 0, "created": 0, "synchronized": 0, "batches": 0}
    async with async_session_maker() as db:
        materializer = MarketDataLookupKeyMaterializer(db)
        for _ in range(args.max_batches):
            result = await materializer.backfill_batch(after_id=cursor, limit=args.batch_size)
            totals["processed"] += result.processed
            totals["created"] += result.created
            totals["synchronized"] += result.synchronized
            totals["batches"] += 1
            cursor = result.next_after_id
            if result.processed == 0:
                break
            if args.apply:
                await db.commit()
                await materializer.publish_staged()
            else:
                await db.rollback()
            if result.processed < args.batch_size:
                break

    print(
        json.dumps(
            {
                **totals,
                "next_after_id": cursor,
                "mode": "applied" if args.apply else "dry_run",
                "dry_run": not bool(args.apply),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    """Execute the bounded backfill command."""
    try:
        return asyncio.run(_run(_arguments()))
    except ValueError:
        print(
            json.dumps({"status": "error", "code": "MARKET_DATA_LOOKUP_BACKFILL_ARGUMENT_INVALID"})
        )
        return 2
    except Exception:
        # SQLAlchemy errors may contain a connection string. This operator
        # boundary deliberately emits a stable non-secret code instead.
        print(json.dumps({"status": "error", "code": "MARKET_DATA_LOOKUP_BACKFILL_FAILED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
