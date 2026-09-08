"""Operator safety contracts for the Iteration 197 exact-key backfill CLI."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.market_data.master_data import LookupKeyBackfillResult
from scripts import backfill_market_data_lookup_keys as backfill_script


class _Session:
    """Minimal rollback/commit recorder for the script's transaction boundary."""

    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class _SessionMaker:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def __call__(self) -> _Session:
        return self.session


class _Materializer:
    def __init__(self, _: _Session, results: list[LookupKeyBackfillResult]) -> None:
        self._results = results
        self.calls: list[dict[str, Any]] = []
        self.publications = 0

    async def backfill_batch(self, *, after_id: str | None, limit: int) -> LookupKeyBackfillResult:
        self.calls.append({"after_id": after_id, "limit": limit})
        return self._results.pop(0)

    async def publish_staged(self) -> None:
        self.publications += 1


def test_lookup_backfill_defaults_to_rollback_only_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare invocation cannot commit master-data projections by accident."""
    monkeypatch.setattr(sys, "argv", ["backfill_market_data_lookup_keys.py"])

    args = backfill_script._arguments()

    assert args.apply is False
    assert args.batch_size == 500
    assert args.max_batches == 1


@pytest.mark.asyncio
async def test_lookup_backfill_dry_run_rolls_back_each_processed_batch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run executes the real materializer path but leaves no persistent projection."""
    session = _Session()
    results = [
        LookupKeyBackfillResult(processed=2, created=1, synchronized=1, next_after_id="id-2"),
        LookupKeyBackfillResult(processed=0, created=0, synchronized=0, next_after_id=None),
    ]
    materializer: _Materializer | None = None

    def materializer_factory(db: _Session) -> _Materializer:
        nonlocal materializer
        materializer = _Materializer(db, results)
        return materializer

    monkeypatch.setattr(backfill_script, "async_session_maker", _SessionMaker(session))
    monkeypatch.setattr(backfill_script, "MarketDataLookupKeyMaterializer", materializer_factory)

    exit_code = await backfill_script._run(
        SimpleNamespace(batch_size=2, max_batches=2, after_id=None, apply=False)
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert session.commits == 0
    assert session.rollbacks == 1
    assert materializer is not None
    assert materializer.publications == 0
    assert materializer.calls == [
        {"after_id": None, "limit": 2},
        {"after_id": "id-2", "limit": 2},
    ]
    assert '"mode": "dry_run"' in output
    assert '"dry_run": true' in output


@pytest.mark.asyncio
async def test_lookup_backfill_apply_is_the_only_commit_path(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The explicit flag records a commit only after a bounded successful batch."""
    session = _Session()
    results = [
        LookupKeyBackfillResult(processed=1, created=1, synchronized=0, next_after_id="id-1"),
    ]
    monkeypatch.setattr(backfill_script, "async_session_maker", _SessionMaker(session))
    materializer: _Materializer | None = None

    def materializer_factory(db: _Session) -> _Materializer:
        nonlocal materializer
        materializer = _Materializer(db, results)
        return materializer

    monkeypatch.setattr(
        backfill_script,
        "MarketDataLookupKeyMaterializer",
        materializer_factory,
    )

    exit_code = await backfill_script._run(
        SimpleNamespace(batch_size=10, max_batches=1, after_id=None, apply=True)
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert session.commits == 1
    assert session.rollbacks == 0
    assert materializer is not None
    assert materializer.publications == 1
    assert '"mode": "applied"' in output
    assert '"dry_run": false' in output
