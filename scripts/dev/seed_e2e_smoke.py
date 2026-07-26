#!/usr/bin/env python3
"""Seed the minimum dataset required by Iteration 175 §6.1 smoke journeys.

Idempotent — safe to run multiple times. Reports skip/create counts on stdout
and exits non-zero only when the database itself is unavailable.

Required seed objects (Requirement 6.5):
  - 1 test user (username=admin, password=admin)
  - 1 strategy draft (named "smoke-strategy")
  - 1 empty knowledge base (named "smoke-kb")
  - 1 completed backtest (id=1) so /backtests/1 has something to render

Total runtime budget: <= 30 seconds (Requirement 6.5).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND_SRC))

START = time.monotonic()


def _log(msg: str) -> None:
    elapsed = time.monotonic() - START
    print(f"[seed_e2e_smoke] {elapsed:6.2f}s {msg}", flush=True)


def main() -> int:
    deadline = 30.0  # seconds

    try:
        from app.config import get_settings

        app_settings = get_settings()
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"FATAL: cannot import backend app.config: {exc!r}",
            file=sys.stderr,
        )
        return 2

    # Late imports so missing optional deps surface as a clear error
    # rather than crashing at module load time.
    try:
        import asyncio

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.utils.security import get_password_hash
    except Exception as exc:  # pragma: no cover - defensive
        print(
            f"FATAL: cannot prepare seed environment: {exc!r}",
            file=sys.stderr,
        )
        return 2

    db_url = os.environ.get("DATABASE_URL") or app_settings.DATABASE_URL
    if not db_url:
        print(
            "FATAL: DATABASE_URL not set and settings.DATABASE_URL missing",
            file=sys.stderr,
        )
        return 2

    engine = create_async_engine(db_url, future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    counts = {
        "users": {"created": 0, "skipped": 0},
        "strategies": {"created": 0, "skipped": 0},
        "knowledge_bases": {"created": 0, "skipped": 0},
        "backtests": {"created": 0, "skipped": 0},
    }

    async def _seed() -> None:  # noqa: PLR0915
        async with Session() as session:
            # --- User
            try:
                from app.models.user import User  # type: ignore
            except Exception as exc:
                _log(f"WARN: cannot import User model — skipping user seed: {exc!r}")
                User = None  # type: ignore

            if User is not None:
                stmt = select(User).where(User.username == "admin")
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    user = User(
                        username="admin",
                        email="admin@example.com",
                        hashed_password=get_password_hash("admin"),
                    )  # type: ignore[arg-type]
                    session.add(user)
                    await session.flush()
                    counts["users"]["created"] += 1
                    _log("created admin user")
                else:
                    counts["users"]["skipped"] += 1
                    _log("admin user exists — skip")

            # --- Strategy draft
            try:
                from app.models.strategy import Strategy  # type: ignore
            except Exception as exc:
                _log(f"WARN: cannot import Strategy model — skipping: {exc!r}")
                Strategy = None  # type: ignore

            if Strategy is not None and User is not None:
                stmt = select(Strategy).where(Strategy.name == "smoke-strategy")
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    strategy = Strategy(  # type: ignore[call-arg]
                        name="smoke-strategy",
                        code="# smoke seed strategy",
                        user_id=1,
                    )
                    session.add(strategy)
                    counts["strategies"]["created"] += 1
                    _log("created smoke-strategy")
                else:
                    counts["strategies"]["skipped"] += 1

            # --- Knowledge base
            try:
                from app.models.knowledge_base import KnowledgeBase  # type: ignore
            except Exception as exc:
                _log(f"WARN: cannot import KnowledgeBase model — skipping: {exc!r}")
                KnowledgeBase = None  # type: ignore

            if KnowledgeBase is not None:
                stmt = select(KnowledgeBase).where(KnowledgeBase.name == "smoke-kb")
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    kb = KnowledgeBase(name="smoke-kb", user_id=1)  # type: ignore[call-arg]
                    session.add(kb)
                    counts["knowledge_bases"]["created"] += 1
                    _log("created smoke-kb")
                else:
                    counts["knowledge_bases"]["skipped"] += 1

            # --- Completed backtest (best-effort)
            try:
                from app.models.backtest import Backtest  # type: ignore
            except Exception as exc:
                _log(f"WARN: cannot import Backtest model — skipping: {exc!r}")
                Backtest = None  # type: ignore

            if Backtest is not None:
                stmt = select(Backtest).limit(1)
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    bt = Backtest(  # type: ignore[call-arg]
                        name="smoke-backtest",
                        status="completed",
                        user_id=1,
                    )
                    session.add(bt)
                    counts["backtests"]["created"] += 1
                    _log("created smoke backtest")
                else:
                    counts["backtests"]["skipped"] += 1

            await session.commit()

    try:
        asyncio.run(asyncio.wait_for(_seed(), timeout=deadline))
    except asyncio.TimeoutError:
        print(
            f"FATAL: seed did not finish within {deadline:.0f}s budget",
            file=sys.stderr,
        )
        return 3
    except Exception as exc:
        print(f"FATAL: seed failed: {exc!r}", file=sys.stderr)
        return 1

    _log(f"summary: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
