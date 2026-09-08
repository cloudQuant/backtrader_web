"""Register Iteration 197 local-first catalog prerequisites after Alembic migration.

The command never fetches market data and never runs from a public request.  It
uses ``DATABASE_URL`` for the canonical application database, records only its
environment-variable name, and registers OpenBB only when a static reviewed
runtime permit exists. ``MARKET_DATA_OPENBB_ALLOWED_MARKETS`` can narrow such
a permit but cannot create one; the initial matrix is explicitly empty.

Examples:
    conda run -n base python scripts/bootstrap_market_data_platform.py
    conda run -n base python scripts/bootstrap_market_data_platform.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.db.database import async_session_maker
from app.services.market_data.bootstrap import (
    MarketDataBootstrapError,
    MarketDataBootstrapSpec,
    MarketDataPlatformBootstrapper,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit catalog registrations. The default performs the same checks then rolls back.",
    )
    return parser.parse_args()


async def _run(*, apply: bool) -> dict[str, object]:
    spec = MarketDataBootstrapSpec.from_settings(get_settings())
    async with async_session_maker() as session:
        try:
            result = await MarketDataPlatformBootstrapper(session).bootstrap(spec)
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
    """Run the bootstrap transaction and print safe structured operator output."""
    args = _arguments()
    try:
        output = asyncio.run(_run(apply=bool(args.apply)))
    except MarketDataBootstrapError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, sort_keys=True))
        return 2
    except Exception:
        # SQLAlchemy driver exceptions can embed a connection URL.  The
        # command is an operator boundary, so preserve a stable non-secret
        # failure code instead of rendering a traceback to stdout.
        print(json.dumps({"status": "error", "code": "MARKET_DATA_BOOTSTRAP_FAILED"}))
        return 1
    print(json.dumps({"status": "ok", **output}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
