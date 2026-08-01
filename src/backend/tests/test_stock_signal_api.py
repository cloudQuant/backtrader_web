"""API visibility and no-order handoff tests for stored stock signals."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from httpx import AsyncClient

from app.db.database import async_session_maker
from app.models.stock_signal import StockSignalPrediction
from app.models.user import User
from app.utils.security import decode_access_token


def _signal(*, key: str, action: str, scope: str = "system") -> StockSignalPrediction:
    record = StockSignalPrediction(
        prediction_key=key,
        owner_scope=scope,
        source="nightly_sse50" if scope == "system" else "manual",
        universe_code="SSE50" if scope == "system" else "MANUAL",
        symbol="600000.SH",
        symbol_name="浦发银行",
        market_type="A股",
        as_of_date=date(2026, 7, 30),
        as_of_at=datetime.now(timezone.utc),
        available_at=datetime.now(timezone.utc),
        next_trading_date=date(2026, 7, 31),
        signal_action=action,
        confidence_score=0.75,
        risk_score=0.3,
        eligibility_status="eligible",
        quality_reasons_json=[],
        data_freshness_json={},
        feature_version="ohlcv-v1",
        decision_policy_version="baseline-v1",
        model_version="deterministic-shadow-v1",
        feature_snapshot_json={},
        policy_snapshot_json={
            "round_trip_cost_bps": 20,
            "buy_success_threshold_bps": 30,
            "sell_success_threshold_bps": 30,
        },
        source_snapshot_hash="a" * 64,
        outcome_status="pending",
    )
    if action == "BUY":
        record.outcome_status = "scored"
        record.horizon_20d_return = 0.05
        record.buy_is_correct_20d = True
    return record


async def _user_id(headers: dict[str, str]) -> str:
    token = headers["Authorization"].split(" ", 1)[1]
    payload = decode_access_token(token)
    assert payload is not None
    return str(payload["sub"])


@pytest.mark.asyncio
async def test_history_is_scoped_and_summary_exposes_only_actioned_denominator(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_user,
) -> None:
    del auth_user
    user_scope = f"user:{await _user_id(auth_headers)}"
    async with async_session_maker() as session:
        other = User(username="other_signal_user", email="other-signal@example.test", hashed_password="x")
        session.add(other)
        await session.flush()
        session.add_all(
            [
                _signal(key="public-sell", action="SELL"),
                _signal(key="own-buy", action="BUY", scope=user_scope),
                _signal(key="other-buy", action="BUY", scope=f"user:{other.id}"),
            ]
        )
        await session.commit()

    history = await client.get(
        "/api/v1/stock-analysis/signals",
        params={"symbol": "600000.SH"},
        headers=auth_headers,
    )
    assert history.status_code == 200, history.text
    payload = history.json()
    assert {item["id"] for item in payload["items"]}
    assert len(payload["items"]) == 2
    assert {item["signal_action"] for item in payload["items"]} == {"BUY", "SELL"}

    first_page = await client.get(
        "/api/v1/stock-analysis/signals",
        params={"symbol": "600000.SH", "limit": 1},
        headers=auth_headers,
    )
    assert first_page.status_code == 200, first_page.text
    first_item = first_page.json()["items"][0]
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None and "|" in cursor
    second_page = await client.get(
        "/api/v1/stock-analysis/signals",
        params={"symbol": "600000.SH", "limit": 1, "cursor": cursor},
        headers=auth_headers,
    )
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["items"][0]["id"] != first_item["id"]

    summary = await client.get(
        "/api/v1/stock-analysis/signals/summary",
        params={"symbol": "600000.SH", "horizon": 20},
        headers=auth_headers,
    )
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["actioned_generated_count"] == 2
    assert summary_payload["actioned_scorable_count"] == 1
    assert summary_payload["actioned_success_rate"] == 1.0


@pytest.mark.asyncio
async def test_opening_preview_is_read_only_action_matrix(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    async with async_session_maker() as session:
        buy = _signal(key="public-buy-preview", action="BUY")
        sell = _signal(key="public-sell-preview", action="SELL")
        sell.symbol = "601398.SH"
        sell.symbol_name = "工商银行"
        session.add_all([buy, sell])
        await session.commit()

    response = await client.post(
        "/api/v1/stock-analysis/signals/opening-actions/preview",
        json={"held_symbols": ["601398.SH"]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["execution_disabled"] is True
    suggestions = {item["symbol"]: item["suggested_action"] for item in payload["actions"]}
    assert suggestions["600000.SH"] == "BUY_AT_OPEN"
    assert suggestions["601398.SH"] == "SELL_AT_OPEN"
