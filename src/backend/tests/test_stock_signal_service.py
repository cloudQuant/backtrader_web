"""Persistence contracts for one point-in-time stock-signal snapshot."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.db.database import async_session_maker
from app.models.stock_signal import StockSignalPrediction
from app.services.stock_signal.service import StockSignalService


def _snapshot(as_of_date: date) -> dict:
    rows: list[dict[str, float | str]] = []
    first_day = as_of_date - timedelta(days=69)
    for offset in range(70):
        close = 10.0 + offset * 0.06
        rows.append(
            {
                "date": (first_day + timedelta(days=offset)).isoformat(),
                "open": close - 0.02,
                "high": close + 0.08,
                "low": close - 0.1,
                "close": close,
                "volume": 1000 + offset,
            }
        )
    return {
        "quote": {"name": "测试股份"},
        "history": {"rows": rows},
        "financials": {"annual": [{"report_date": "2026-03-31", "roe": 10.0}]},
        "news": {"items": [{"published_at": as_of_date.isoformat(), "headline": "经营数据披露"}]},
    }


@pytest.mark.asyncio
async def test_prediction_key_is_idempotent_and_keeps_versioned_snapshot() -> None:
    as_of_date = date(2026, 6, 10)
    async with async_session_maker() as session:
        service = StockSignalService(session)
        first = await service.create_prediction(
            snapshot=_snapshot(as_of_date),
            symbol="600000.SH",
            market_type="A股",
            as_of_date=as_of_date,
            owner_scope="user:test-user",
            source="manual",
            universe_code="MANUAL",
            next_trading_date=date(2026, 6, 11),
        )
        await session.commit()

        second = await service.create_prediction(
            snapshot=_snapshot(as_of_date),
            symbol="600000.SH",
            market_type="A股",
            as_of_date=as_of_date,
            owner_scope="user:test-user",
            source="manual",
            universe_code="MANUAL",
            next_trading_date=date(2026, 6, 11),
        )

        count = await session.scalar(select(func.count()).select_from(StockSignalPrediction))

    assert first.id == second.id
    assert count == 1
    assert first.feature_version == "ohlcv-v1"
    assert first.decision_policy_version == "baseline-v1"
    assert first.source_snapshot_hash
    assert first.eligibility_status == "eligible"


@pytest.mark.asyncio
async def test_create_prediction_with_shadow_supports_off_and_enforce() -> None:
    as_of_date = date(2026, 6, 10)
    async with async_session_maker() as session:
        service = StockSignalService(session)
        shadows: list[str] = []

        async def shadow_write(prediction: StockSignalPrediction) -> None:
            shadows.append(prediction.id)

        prediction, off_outcome = await service.create_prediction_with_shadow(
            snapshot=_snapshot(as_of_date),
            symbol="600001.SH",
            market_type="A股",
            as_of_date=as_of_date,
            owner_scope="user:dual-write",
            source="manual",
            universe_code="MANUAL",
            shadow_write=shadow_write,
            dual_write_mode="OFF",
        )
        await session.commit()

    assert off_outcome.shadow_succeeded is False
    assert shadows == []

    async with async_session_maker() as session:
        service = StockSignalService(session)
        shadows = []
        prediction, enforce_outcome = await service.create_prediction_with_shadow(
            snapshot=_snapshot(as_of_date),
            symbol="600002.SH",
            market_type="A股",
            as_of_date=as_of_date,
            owner_scope="user:dual-write",
            source="manual",
            universe_code="MANUAL",
            shadow_write=shadow_write,
            dual_write_mode="ENFORCE",
        )
        await session.commit()

    assert enforce_outcome.shadow_succeeded is True
    assert shadows == [prediction.id]
