"""OFF/SHADOW/ENFORCE contracts for legacy stock signal dual-write."""

import pytest

from app.services.asset_research.stock_dual_write import (
    DualWriteMode,
    StockDualWriteCoordinator,
)


@pytest.mark.asyncio
async def test_off_mode_writes_only_legacy_signal() -> None:
    calls: list[str] = []

    async def primary() -> None:
        calls.append("primary")

    async def shadow() -> None:
        calls.append("shadow")

    outcome = await StockDualWriteCoordinator(DualWriteMode.OFF).write(
        primary_write=primary,
        shadow_write=shadow,
    )

    assert calls == ["primary"]
    assert outcome.operation_succeeded is True


@pytest.mark.asyncio
async def test_shadow_mode_does_not_break_legacy_when_new_write_fails() -> None:
    async def primary() -> None:
        return None

    async def shadow() -> None:
        raise RuntimeError("SHADOW_UNAVAILABLE")

    outcome = await StockDualWriteCoordinator(DualWriteMode.SHADOW).write(
        primary_write=primary,
        shadow_write=shadow,
    )

    assert outcome.primary_succeeded is True
    assert outcome.shadow_succeeded is False
    assert outcome.shadow_error == "SHADOW_UNAVAILABLE"
    assert outcome.operation_succeeded is True


@pytest.mark.asyncio
async def test_enforce_mode_fails_when_new_write_fails() -> None:
    async def primary() -> None:
        return None

    async def shadow() -> None:
        raise RuntimeError("SHADOW_UNAVAILABLE")

    with pytest.raises(RuntimeError, match="SHADOW_WRITE_FAILED"):
        await StockDualWriteCoordinator(DualWriteMode.ENFORCE).write(
            primary_write=primary,
            shadow_write=shadow,
        )
