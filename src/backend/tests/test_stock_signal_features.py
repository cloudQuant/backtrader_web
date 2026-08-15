"""Focused acceptance tests for feature, quality, and policy contracts."""

from __future__ import annotations

from datetime import date, timedelta

from app.services.stock_signal.decision_policy import SignalPolicy, decide_snapshot
from app.services.stock_signal.features import calculate_features
from app.services.stock_signal.quality import DataQualityGate
from app.services.stock_signal.types import DataQualityAssessment, SignalFeatures


def _rows(*, count: int = 70, start: float = 10.0) -> list[dict[str, float | str]]:
    first_day = date(2026, 1, 1)
    rows: list[dict[str, float | str]] = []
    for index in range(count):
        close = start + index * 0.08
        rows.append(
            {
                "date": (first_day + timedelta(days=index)).isoformat(),
                "open": close - 0.03,
                "high": close + 0.12,
                "low": close - 0.15,
                "close": close,
                "volume": 1000 + index * 10,
            }
        )
    return rows


def _snapshot(rows: list[dict[str, float | str]]) -> dict:
    latest = str(rows[-1]["date"])
    return {
        "history": {"rows": rows},
        "financials": {"annual": [{"report_date": "2025-12-31", "roe": 12.0}]},
        "news": {"items": [{"published_at": latest, "headline": "测试新闻"}]},
    }


def test_features_are_calculated_from_real_ohlcv_rows() -> None:
    features = calculate_features(_rows())

    assert features.bar_count == 70
    assert features.return_20 is not None and features.return_20 > 0
    assert features.ma20_gap is not None and features.ma20_gap > 0
    assert features.rsi14 is not None and features.rsi14 > 50
    assert features.volatility20 is not None
    assert features.atr14_ratio is not None
    assert "missing_ohlc_for_atr" not in features.reasons


def test_quality_gate_rejects_stale_or_short_prices_instead_of_imputing_zero() -> None:
    rows = _rows(count=1)
    features = calculate_features(rows)
    assessment = DataQualityGate().assess(
        snapshot=_snapshot(rows),
        features=features,
        as_of_date=date(2026, 3, 11),
    )

    assert assessment.status == "rejected"
    assert "stale_or_missing_market_close" in assessment.reasons
    assert "insufficient_history_bars" in assessment.reasons


def test_missing_news_degrades_to_watch_not_a_neutral_direction() -> None:
    rows = _rows()
    snapshot = _snapshot(rows)
    snapshot["news"] = {"items": []}
    decision, _, quality = decide_snapshot(
        snapshot,
        as_of_date=date.fromisoformat(str(rows[-1]["date"])),
    )

    assert quality.status == "degraded"
    assert "news_unavailable" in quality.reasons
    assert decision.action == "WATCH"
    assert decision.buy_probability is None
    assert decision.sell_probability is None


def test_policy_emits_direction_only_when_eligible() -> None:
    quality = DataQualityAssessment("eligible", (), {})
    bullish = SignalFeatures(
        as_of_date=date(2026, 3, 11),
        latest_close=15.0,
        latest_open=14.9,
        return_1=0.02,
        return_5=0.06,
        return_20=0.16,
        return_60=0.3,
        ma5_gap=0.03,
        ma20_gap=0.08,
        rsi14=64.0,
        atr14_ratio=0.01,
        volatility20=0.01,
        volume_zscore20=1.0,
        range_position20=0.9,
        bar_count=70,
    )
    bearish = SignalFeatures(
        **{
            **bullish.__dict__,
            "return_1": -0.03,
            "return_5": -0.08,
            "return_20": -0.2,
            "ma5_gap": -0.05,
            "ma20_gap": -0.1,
            "rsi14": 30.0,
            "volume_zscore20": -1.0,
        }
    )

    policy = SignalPolicy()
    assert policy.decide(features=bullish, quality=quality).action == "BUY"
    assert policy.decide(features=bearish, quality=quality).action == "SELL"
