"""Typed domain values shared by the signal pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

SignalAction = Literal["BUY", "SELL", "WATCH"]
EligibilityStatus = Literal["eligible", "degraded", "rejected"]

ACTION_LABELS: dict[SignalAction, str] = {
    "BUY": "买入",
    "SELL": "卖出",
    "WATCH": "观望",
}


@dataclass(frozen=True)
class SignalFeatures:
    """Point-in-time price features with explicit missing-field reasons."""

    as_of_date: date | None
    latest_close: float | None
    latest_open: float | None
    return_1: float | None
    return_5: float | None
    return_20: float | None
    return_60: float | None
    ma5_gap: float | None
    ma20_gap: float | None
    rsi14: float | None
    atr14_ratio: float | None
    volatility20: float | None
    volume_zscore20: float | None
    range_position20: float | None
    bar_count: int
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def snapshot(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["as_of_date"] = self.as_of_date.isoformat() if self.as_of_date else None
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True)
class DataQualityAssessment:
    """Eligibility result which never treats unavailable data as neutral."""

    status: EligibilityStatus
    reasons: tuple[str, ...]
    freshness: dict[str, Any]


@dataclass(frozen=True)
class SignalDecision:
    """A serializable, policy-authoritative signal decision."""

    action: SignalAction
    confidence_score: float
    buy_probability: float | None
    sell_probability: float | None
    watch_probability: float | None
    expected_excess_return: float | None
    risk_score: float
    eligibility_status: EligibilityStatus
    quality_reasons: tuple[str, ...]
    feature_version: str
    decision_policy_version: str
    model_version: str
    policy_snapshot: dict[str, Any]
    reasoning: str

    @property
    def action_label(self) -> str:
        return ACTION_LABELS[self.action]

    def payload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "label": self.action_label,
            "confidence": self.confidence_score,
            "confidence_score": self.confidence_score,
            "buy_probability": self.buy_probability,
            "sell_probability": self.sell_probability,
            "watch_probability": self.watch_probability,
            "expected_excess_return": self.expected_excess_return,
            "risk_score": self.risk_score,
            "eligibility_status": self.eligibility_status,
            "quality_reasons": list(self.quality_reasons),
            "feature_version": self.feature_version,
            "decision_policy_version": self.decision_policy_version,
            "model_version": self.model_version,
            "policy_snapshot": self.policy_snapshot,
            "reasoning": self.reasoning,
        }
