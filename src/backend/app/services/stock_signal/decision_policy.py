"""A transparent, versioned baseline policy for stock research signals."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from app.services.stock_signal.features import FEATURE_VERSION, calculate_features
from app.services.stock_signal.quality import DataQualityGate
from app.services.stock_signal.types import (
    DataQualityAssessment,
    SignalAction,
    SignalDecision,
    SignalFeatures,
)


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-12.0, min(12.0, value))))


def _or_zero(value: float | None) -> float:
    return value if value is not None else 0.0


class SignalPolicy:
    """Policy authority for `BUY`, `SELL`, and `WATCH` labels.

    The policy is deliberately deterministic. It is an auditable shadow baseline,
    not a claim that the score is an already-validated predictive model.
    """

    decision_policy_version = "baseline-v1"
    model_version = "deterministic-shadow-v1"

    def __init__(
        self,
        *,
        round_trip_cost_bps: float = 20.0,
        buy_success_threshold_bps: float = 30.0,
        sell_success_threshold_bps: float = 30.0,
    ) -> None:
        self.round_trip_cost_bps = round_trip_cost_bps
        self.buy_success_threshold_bps = buy_success_threshold_bps
        self.sell_success_threshold_bps = sell_success_threshold_bps

    def snapshot(self) -> dict[str, Any]:
        return {
            "round_trip_cost_bps": self.round_trip_cost_bps,
            "buy_success_threshold_bps": self.buy_success_threshold_bps,
            "sell_success_threshold_bps": self.sell_success_threshold_bps,
            "buy_probability_threshold": 0.62,
            "sell_probability_threshold": 0.62,
            "max_buy_risk_score": 0.65,
            "forced_sell_risk_score": 0.78,
        }

    def decide(
        self,
        *,
        features: SignalFeatures,
        quality: DataQualityAssessment,
    ) -> SignalDecision:
        if quality.status != "eligible":
            reason = "数据质量未达可交易信号门槛，输出观望。"
            return SignalDecision(
                action="WATCH",
                confidence_score=0.5,
                buy_probability=None,
                sell_probability=None,
                watch_probability=1.0,
                expected_excess_return=None,
                risk_score=1.0 if quality.status == "rejected" else 0.7,
                eligibility_status=quality.status,
                quality_reasons=quality.reasons,
                feature_version=FEATURE_VERSION,
                decision_policy_version=self.decision_policy_version,
                model_version=self.model_version,
                policy_snapshot=self.snapshot(),
                reasoning=reason,
            )

        trend = (
            0.38 * _clamp(_or_zero(features.return_20) / 0.12, -1.0, 1.0)
            + 0.22 * _clamp(_or_zero(features.ma20_gap) / 0.06, -1.0, 1.0)
            + 0.16 * _clamp(_or_zero(features.return_5) / 0.05, -1.0, 1.0)
            + 0.12 * _clamp((_or_zero(features.rsi14) - 50.0) / 30.0, -1.0, 1.0)
            + 0.12 * _clamp(_or_zero(features.volume_zscore20) / 2.0, -1.0, 1.0)
        )
        volatility = _or_zero(features.volatility20)
        atr = _or_zero(features.atr14_ratio)
        overbought = _clamp((_or_zero(features.rsi14) - 70.0) / 30.0)
        risk_score = _clamp(0.28 + volatility * 7.0 + atr * 5.0 + overbought * 0.15)
        buy_probability = _sigmoid(2.7 * trend - 2.0 * max(0.0, risk_score - 0.45))
        sell_probability = _sigmoid(-2.7 * trend + 2.5 * max(0.0, risk_score - 0.55))
        watch_probability = _clamp(1.0 - abs(buy_probability - sell_probability))
        expected_excess_return = trend * 0.04 - risk_score * 0.01

        action: SignalAction = "WATCH"
        if risk_score >= 0.78 or sell_probability >= 0.62:
            action = "SELL"
        elif buy_probability >= 0.62 and risk_score <= 0.65:
            action = "BUY"

        confidence = _clamp(max(buy_probability, sell_probability, watch_probability))
        direction = {"BUY": "趋势和量价特征偏强", "SELL": "风险或趋势特征偏弱", "WATCH": "方向证据不足"}[action]
        return SignalDecision(
            action=action,
            confidence_score=confidence,
            buy_probability=buy_probability,
            sell_probability=sell_probability,
            watch_probability=watch_probability,
            expected_excess_return=expected_excess_return,
            risk_score=risk_score,
            eligibility_status="eligible",
            quality_reasons=(),
            feature_version=FEATURE_VERSION,
            decision_policy_version=self.decision_policy_version,
            model_version=self.model_version,
            policy_snapshot=self.snapshot(),
            reasoning=f"{direction}；信号由 {self.decision_policy_version} 的结构化规则生成。",
        )


def decide_snapshot(
    snapshot: dict[str, Any],
    *,
    as_of_date: date,
    policy: SignalPolicy | None = None,
    quality_gate: DataQualityGate | None = None,
) -> tuple[SignalDecision, SignalFeatures, DataQualityAssessment]:
    """Evaluate a snapshot without persistence for reports and test fixtures."""
    rows = (snapshot.get("history") or {}).get("rows") or []
    features = calculate_features(rows if isinstance(rows, list) else [])
    gate = quality_gate or DataQualityGate()
    quality = gate.assess(snapshot=snapshot, features=features, as_of_date=as_of_date)
    decision = (policy or SignalPolicy()).decide(features=features, quality=quality)
    return decision, features, quality
