"""Unified risk gate checks for paper-to-live promotion and live starts."""

from __future__ import annotations

from typing import Any

from app.services.trading_asset_info_service import symbol_aliases

_DEFAULT_RISK_LIMITS: dict[str, Any] = {
    "max_position_pct": 0.3,
    "max_single_order_value": 10000.0,
    "max_daily_loss_pct": 0.05,
    "max_drawdown_pct": 0.2,
    "max_margin_usage_pct": 0.8,
    "max_slippage_bps": 50.0,
    "blacklisted_symbols": [],
}


class RiskGateService:
    """Evaluate unified pre-live and pre-run risk gates.

    The returned evaluation rows intentionally follow the platform quality-gate
    shape so AI research, handoff packages, and runtime checks can expose the
    same evidence contract.
    """

    def evaluate_live_preparation(
        self,
        *,
        record: Any,
        package: Any,
        request: Any | None = None,
        source_unit: Any | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether an approved AI handoff may materialize a live unit."""
        symbol = str(getattr(record, "symbol", "") or "").strip()
        metrics = _safe_dict(getattr(record, "best_metrics", None))
        risk_limits = self._risk_limits(
            _safe_dict(getattr(record, "backtest_environment", None)).get("risk_limits"),
            _safe_dict(getattr(record, "paper_handoff", None)).get("risk_limits"),
            _nested(_safe_dict(getattr(record, "paper_handoff", None)), "gateway_config", "risk_limits"),
            _safe_dict(getattr(source_unit, "unit_settings", None)).get("risk_limits"),
            _safe_dict(getattr(source_unit, "gateway_config", None)).get("risk_limits"),
            _safe_dict(getattr(request, "gateway_config", None)).get("risk_limits")
            if request is not None
            else None,
        )
        approval = getattr(package, "approval", None)
        deployment_blockers = [
            str(item).strip()
            for item in (getattr(package, "deployment_blockers", None) or [])
            if str(item).strip()
        ]
        evaluations = [
            self._evaluation(
                "live_handoff_approved",
                "实盘交接已审批",
                bool(
                    getattr(package, "ready_for_live", False)
                    and getattr(package, "status", "") == "approved_for_live"
                    and getattr(approval, "approved", False)
                ),
                actual=getattr(package, "status", None),
                threshold="approved_for_live",
                operator="==",
                message="实盘交接包必须通过人工审批。",
            ),
            self._evaluation(
                "risk_limits_confirmed",
                "风险限额已确认",
                bool(getattr(approval, "risk_limit_confirmed", False)),
                actual=getattr(approval, "risk_limit_confirmed", False),
                threshold=True,
                operator="==",
                message="审批人必须确认实盘风险限额。",
            ),
            self._evaluation(
                "deployment_blockers_clear",
                "实盘阻断项已清零",
                not deployment_blockers,
                actual=len(deployment_blockers),
                threshold=0,
                operator="==",
                message="实盘交接包仍存在阻断项。",
            ),
            *self._market_risk_evaluations(symbol=symbol, metrics=metrics, risk_limits=risk_limits),
        ]
        return self._decision(evaluations, risk_limits=risk_limits)

    def evaluate_trading_unit_pre_run(
        self,
        unit: Any,
        *,
        workspace_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether a strategy unit may be started in trading workspace."""
        trading_mode = str(getattr(unit, "trading_mode", "") or "").strip().lower()
        symbol = str(getattr(unit, "symbol", "") or "").strip()
        unit_settings = _safe_dict(getattr(unit, "unit_settings", None))
        gateway_config = _safe_dict(getattr(unit, "gateway_config", None))
        data_config = _safe_dict(getattr(unit, "data_config", None))
        metrics = _safe_dict(getattr(unit, "metrics_snapshot", None))
        handoff = _safe_dict(unit_settings.get("ai_research_live_handoff"))
        risk_gate = _safe_dict(unit_settings.get("live_risk_gate"))
        risk_limits = self._risk_limits(
            _safe_dict(workspace_settings).get("risk_limits"),
            unit_settings.get("risk_limits"),
            gateway_config.get("risk_limits"),
            risk_gate.get("risk_limits"),
        )

        evaluations: list[dict[str, Any]] = []
        is_ai_live_unit = bool(
            trading_mode == "live"
            and (
                handoff
                or data_config.get("ai_research_run_id")
                or unit_settings.get("ai_research_run_id")
            )
        )
        if is_ai_live_unit:
            approval = _safe_dict(handoff.get("approval"))
            evaluations.extend(
                [
                    self._evaluation(
                        "live_handoff_approved",
                        "AI实盘交接已审批",
                        bool(
                            handoff.get("live_handoff_status") == "approved_for_live"
                            and approval.get("approved") is True
                        ),
                        actual=handoff.get("live_handoff_status"),
                        threshold="approved_for_live",
                        operator="==",
                        message="AI 投研实盘单元必须来自已审批的实盘交接包。",
                    ),
                    self._evaluation(
                        "risk_limits_confirmed",
                        "AI实盘风险限额已确认",
                        approval.get("risk_limit_confirmed") is True,
                        actual=approval.get("risk_limit_confirmed"),
                        threshold=True,
                        operator="==",
                        message="AI 投研实盘单元启动前必须确认风险限额。",
                    ),
                ]
            )
            if risk_gate:
                evaluations.append(
                    self._evaluation(
                        "prepared_risk_gate_passed",
                        "实盘准备风控已通过",
                        risk_gate.get("passed") is True,
                        actual=risk_gate.get("status"),
                        threshold="passed",
                        operator="==",
                        message="实盘准备阶段风控检查未通过或缺少通过证据。",
                    )
                )

        evaluations.extend(
            self._market_risk_evaluations(symbol=symbol, metrics=metrics, risk_limits=risk_limits)
        )
        return self._decision(evaluations, risk_limits=risk_limits)

    def assert_trading_unit_pre_run(
        self,
        unit: Any,
        *,
        workspace_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Raise ValueError when the trading-unit pre-run risk gate fails."""
        decision = self.evaluate_trading_unit_pre_run(
            unit,
            workspace_settings=workspace_settings,
        )
        if not decision["passed"]:
            raise ValueError(_risk_gate_error(decision))
        return decision

    def _market_risk_evaluations(
        self,
        *,
        symbol: str,
        metrics: dict[str, Any],
        risk_limits: dict[str, Any],
    ) -> list[dict[str, Any]]:
        max_drawdown_pct = _safe_float(risk_limits.get("max_drawdown_pct"), 0.0)
        max_margin_usage_pct = _safe_float(risk_limits.get("max_margin_usage_pct"), 0.0)
        max_slippage_bps = _safe_float(risk_limits.get("max_slippage_bps"), 0.0)
        planned_position_pct = _safe_float(risk_limits.get("planned_position_pct"), 0.0)
        planned_order_value = _safe_float(risk_limits.get("planned_order_value"), 0.0)
        planned_margin_usage_pct = _safe_float(risk_limits.get("planned_margin_usage_pct"), 0.0)
        actual_slippage_bps = _safe_float(metrics.get("actual_slippage_bps"), 0.0)
        max_daily_loss_pct = _safe_float(risk_limits.get("max_daily_loss_pct"), 0.0)
        current_daily_loss_pct = abs(_safe_float(metrics.get("daily_loss_pct"), 0.0))
        max_single_order_value = _safe_float(risk_limits.get("max_single_order_value"), 0.0)
        max_position_pct = _safe_float(risk_limits.get("max_position_pct"), 0.0)
        observed_drawdown_pct = _drawdown_pct(metrics)

        return [
            self._evaluation(
                "blacklisted_symbol",
                "黑名单资产检查",
                not _symbol_in_list(symbol, risk_limits.get("blacklisted_symbols")),
                actual=symbol,
                threshold=list(risk_limits.get("blacklisted_symbols") or []),
                operator="not_in",
                message=f"{symbol} 在禁止交易列表中。",
            ),
            self._evaluation(
                "max_position",
                "最大仓位",
                max_position_pct <= 0 or planned_position_pct <= max_position_pct,
                actual=planned_position_pct,
                threshold=max_position_pct,
                operator="<=",
                message="计划仓位超过最大仓位限制。",
            ),
            self._evaluation(
                "max_single_order_value",
                "最大单笔金额",
                max_single_order_value <= 0 or planned_order_value <= max_single_order_value,
                actual=planned_order_value,
                threshold=max_single_order_value,
                operator="<=",
                message="计划单笔金额超过限制。",
            ),
            self._evaluation(
                "max_daily_loss",
                "最大日亏损",
                max_daily_loss_pct <= 0 or current_daily_loss_pct <= max_daily_loss_pct,
                actual=current_daily_loss_pct,
                threshold=max_daily_loss_pct,
                operator="<=",
                message="当日亏损超过限制。",
            ),
            self._evaluation(
                "max_drawdown",
                "最大回撤",
                max_drawdown_pct <= 0 or observed_drawdown_pct <= max_drawdown_pct,
                actual=observed_drawdown_pct,
                threshold=max_drawdown_pct,
                operator="<=",
                message="策略回撤超过实盘准入限制。",
            ),
            self._evaluation(
                "margin_usage",
                "保证金占用",
                max_margin_usage_pct <= 0 or planned_margin_usage_pct <= max_margin_usage_pct,
                actual=planned_margin_usage_pct,
                threshold=max_margin_usage_pct,
                operator="<=",
                message="计划保证金占用超过限制。",
            ),
            self._evaluation(
                "actual_slippage",
                "实际滑点",
                max_slippage_bps <= 0 or actual_slippage_bps <= max_slippage_bps,
                actual=actual_slippage_bps,
                threshold=max_slippage_bps,
                operator="<=",
                message="实际滑点超过限制。",
            ),
        ]

    def _risk_limits(self, *payloads: Any) -> dict[str, Any]:
        merged = dict(_DEFAULT_RISK_LIMITS)
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if value not in (None, ""):
                    merged[str(key)] = value
        return merged

    @staticmethod
    def _evaluation(
        key: str,
        label: str,
        passed: bool,
        *,
        actual: Any,
        threshold: Any,
        operator: str,
        message: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "actual": actual,
            "threshold": threshold,
            "operator": operator,
            "passed": bool(passed),
            "severity": "error" if not passed else "info",
            "message": "" if passed else message,
        }

    @staticmethod
    def _decision(
        evaluations: list[dict[str, Any]],
        *,
        risk_limits: dict[str, Any],
    ) -> dict[str, Any]:
        passed = all(bool(item.get("passed")) for item in evaluations)
        blockers = [
            str(item.get("message") or item.get("label") or item.get("key"))
            for item in evaluations
            if not item.get("passed")
        ]
        return {
            "status": "passed" if passed else "blocked",
            "passed": passed,
            "evaluations": evaluations,
            "blockers": list(dict.fromkeys(item for item in blockers if item)),
            "risk_limits": dict(risk_limits),
        }


def _risk_gate_error(decision: dict[str, Any]) -> str:
    blockers = [str(item).strip() for item in decision.get("blockers") or [] if str(item).strip()]
    detail = "；".join(blockers[:3]) if blockers else "存在未通过的风控项"
    return f"风控检查未通过: {detail}"


def _safe_dict(value: Any = None) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _drawdown_pct(metrics: dict[str, Any]) -> float:
    raw = _safe_float(
        metrics.get("max_drawdown")
        if metrics.get("max_drawdown") not in (None, "")
        else metrics.get("max_drawdown_pct"),
        0.0,
    )
    raw = abs(raw)
    return raw / 100.0 if raw > 1.0 else raw


def _symbol_in_list(symbol: str, values: Any) -> bool:
    blocked = [str(item).strip() for item in values or [] if str(item).strip()]
    if not symbol or not blocked:
        return False
    symbol_keys = {item.upper() for item in symbol_aliases(symbol)}
    for item in blocked:
        if symbol_keys & {alias.upper() for alias in symbol_aliases(item)}:
            return True
    return False
