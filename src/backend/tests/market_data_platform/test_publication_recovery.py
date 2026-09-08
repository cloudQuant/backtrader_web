"""Operator recovery contracts for stranded Iteration 197 visibility receipts."""

from __future__ import annotations

import pytest

from scripts import recover_market_data_publications as recovery_script


class _SessionContext:
    """A minimal async session factory replacement for command wiring tests."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_recovery_command_defaults_to_one_bounded_dry_run_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operational script never applies hidden receipt changes by default."""
    calls: list[tuple[object, int, bool]] = []

    class _Manager:
        def __init__(self, session: object) -> None:
            self._session = session

        async def recover_pending(self, *, limit: int, dry_run: bool) -> tuple[str, ...]:
            calls.append((self._session, limit, dry_run))
            return ("receipt-a", "receipt-b")

    monkeypatch.setattr(recovery_script, "async_session_maker", _SessionContext)
    monkeypatch.setattr(recovery_script, "MarketDataPublicationManager", _Manager)

    arguments = recovery_script._arguments([])
    result = await recovery_script._run(limit=7, apply=bool(arguments.apply))

    assert arguments.apply is False
    assert result == {"mode": "dry_run", "receipt_count": 2}
    assert len(calls) == 1
    assert calls[0][1:] == (7, True)


@pytest.mark.asyncio
async def test_recovery_command_requires_the_explicit_apply_switch_for_visibility_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The command passes ``dry_run=False`` only after an operator supplied --apply."""
    dry_run_values: list[bool] = []

    class _Manager:
        def __init__(self, _session: object) -> None:
            pass

        async def recover_pending(self, *, limit: int, dry_run: bool) -> tuple[str, ...]:
            assert limit == 3
            dry_run_values.append(dry_run)
            return ()

    monkeypatch.setattr(recovery_script, "async_session_maker", _SessionContext)
    monkeypatch.setattr(recovery_script, "MarketDataPublicationManager", _Manager)

    arguments = recovery_script._arguments(["--apply", "--limit", "3"])
    result = await recovery_script._run(limit=arguments.limit, apply=bool(arguments.apply))

    assert result == {"mode": "applied", "receipt_count": 0}
    assert dry_run_values == [False]
