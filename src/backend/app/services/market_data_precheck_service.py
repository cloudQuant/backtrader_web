"""Backtest market data precheck service."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

from app.schemas.market_data_trust import (
    DataPrecheckRequest,
    DataPrecheckResponse,
    QualityGateEvaluation,
)
from app.services.asset_spec_service import (
    AssetSpecService,
    get_asset_spec_service,
    infer_asset_type,
)
from app.services.backtest.execution_model import ExecutionModel
from app.services.market_data_coverage_service import (
    MarketDataCoverageService,
    get_market_data_coverage_service,
)


class MarketDataPrecheckService:
    """Validate whether an asset/timeframe can be backtested credibly."""

    def __init__(
        self,
        *,
        asset_spec_service: AssetSpecService | None = None,
        coverage_service: MarketDataCoverageService | None = None,
    ) -> None:
        self.asset_spec_service = asset_spec_service or get_asset_spec_service()
        self.coverage_service = coverage_service or get_market_data_coverage_service()

    async def precheck(self, request: DataPrecheckRequest) -> DataPrecheckResponse:
        asset_type = infer_asset_type(request.symbol, request.asset_type)
        provider = request.provider or "local_csv"
        spec = await self.asset_spec_service.get_or_create(
            symbol=request.symbol,
            asset_type=asset_type,
        )
        coverage = await self.coverage_service.get_best_coverage(
            asset_type=asset_type,
            symbol=request.symbol,
            timeframe=request.timeframe,
            provider=provider,
        )
        reports = await self.coverage_service.list_quality_reports(
            asset_type=asset_type,
            symbol=request.symbol,
            timeframe=request.timeframe,
            provider=provider,
            limit=20,
        )

        evaluations: list[QualityGateEvaluation] = []
        reasons: list[str] = []
        warnings: list[str] = []

        spec_payload = spec.model_dump(mode="python") if spec is not None else {}
        execution_model = ExecutionModel.from_asset_spec(spec_payload)
        evaluations.extend(_asset_spec_evaluations(asset_type, execution_model, spec_payload))

        if coverage is None:
            warnings.append("未找到该资产/周期的数据覆盖记录，无法证明数据完整性。")
            evaluations.append(
                QualityGateEvaluation(
                    key="data_coverage_available",
                    label="数据覆盖记录",
                    actual=0,
                    threshold=1,
                    operator=">=",
                    passed=False,
                    severity="warning",
                    message="没有覆盖率记录；可先刷新覆盖矩阵或补齐行情数据。",
                )
            )
        else:
            evaluations.extend(
                _coverage_evaluations(
                    coverage.model_dump(mode="python"),
                    start_date=request.start_date,
                    end_date=request.end_date,
                )
            )

        for report in reports:
            severity = str(report.severity)
            message = f"{report.issue_type} x {report.issue_count}"
            if severity == "error":
                reasons.append(message)
            else:
                warnings.append(message)

        for item in evaluations:
            if item.passed:
                continue
            if item.severity == "error":
                reasons.append(item.message or f"{item.label} 未通过")
            else:
                warnings.append(item.message or f"{item.label} 需要关注")

        deduped_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
        deduped_warnings = list(dict.fromkeys(warning for warning in warnings if warning))
        status = "failed" if deduped_reasons else "warning" if deduped_warnings else "pass"
        return DataPrecheckResponse(
            passed=not deduped_reasons,
            status=status,
            asset_type=asset_type,
            symbol=request.symbol,
            timeframe=request.timeframe,
            provider=provider,
            reasons=deduped_reasons,
            warnings=deduped_warnings,
            asset_spec=spec,
            coverage=coverage,
            quality_reports=reports,
            gate_evaluations=evaluations,
        )


def _asset_spec_evaluations(
    asset_type: str,
    execution_model: ExecutionModel,
    spec_payload: dict[str, Any],
) -> list[QualityGateEvaluation]:
    evaluations = [
        QualityGateEvaluation(
            key="contract_multiplier",
            label="合约乘数",
            actual=execution_model.contract_multiplier,
            threshold=0,
            operator=">",
            passed=execution_model.contract_multiplier > 0,
            severity="error" if asset_type in {"futures", "option"} else "warning",
            message="缺少可用合约乘数。",
        ),
        QualityGateEvaluation(
            key="min_order_size",
            label="最小下单量",
            actual=execution_model.min_order_size,
            threshold=0,
            operator=">",
            passed=execution_model.min_order_size > 0,
            severity="error",
            message="缺少最小下单量。",
        ),
        QualityGateEvaluation(
            key="trading_cost",
            label="交易成本",
            actual=execution_model.commission_rate or execution_model.commission_fixed,
            threshold=0,
            operator=">=",
            passed=(
                execution_model.commission_rate >= 0
                or execution_model.commission_fixed >= 0
                or bool(spec_payload.get("commission_fixed"))
            ),
            severity="warning",
            message="手续费未确认，将使用默认成本假设。",
        ),
    ]
    if asset_type in {"futures", "option"}:
        margin = execution_model.margin_rate
        evaluations.append(
            QualityGateEvaluation(
                key="margin_rate",
                label="保证金",
                actual=margin,
                threshold=0,
                operator=">",
                passed=margin is not None and margin > 0,
                severity="error",
                message="期货/期权缺少保证金率。",
            )
        )
    return evaluations


def _coverage_evaluations(
    coverage: dict[str, Any],
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[QualityGateEvaluation]:
    missing_ratio = float(coverage.get("missing_ratio") or 0.0)
    quality_status = str(coverage.get("quality_status") or "unknown")
    evaluations = [
        QualityGateEvaluation(
            key="row_count",
            label="行情行数",
            actual=int(coverage.get("row_count") or 0),
            threshold=30,
            operator=">=",
            passed=int(coverage.get("row_count") or 0) >= 30,
            severity="error",
            message="可用行情少于 30 行，样本不足。",
        ),
        QualityGateEvaluation(
            key="missing_ratio",
            label="缺失率",
            actual=missing_ratio,
            threshold=0.35,
            operator="<=",
            passed=missing_ratio <= 0.35,
            severity="error",
            message=f"行情缺失率 {missing_ratio:.2%} 过高。",
        ),
        QualityGateEvaluation(
            key="quality_status",
            label="质量状态",
            actual=quality_status,
            threshold="failed",
            operator="!=",
            passed=quality_status != "failed",
            severity="error",
            message="数据质量检查存在阻断级问题。",
        ),
    ]
    evaluations.extend(_date_range_evaluations(coverage, start_date=start_date, end_date=end_date))
    return evaluations


def _date_range_evaluations(
    coverage: dict[str, Any],
    *,
    start_date: str | None,
    end_date: str | None,
) -> list[QualityGateEvaluation]:
    requested_start = _parse_date(start_date)
    requested_end = _parse_date(end_date)
    coverage_start = _parse_date(coverage.get("start_date"))
    coverage_end = _parse_date(coverage.get("end_date"))
    if requested_start is None and requested_end is None:
        return []
    passed = True
    if requested_start is not None and coverage_start is not None:
        passed = passed and coverage_start <= requested_start
    if requested_end is not None and coverage_end is not None:
        passed = passed and coverage_end >= requested_end
    return [
        QualityGateEvaluation(
            key="requested_date_range",
            label="请求区间覆盖",
            actual=f"{coverage.get('start_date') or '-'}~{coverage.get('end_date') or '-'}",
            threshold=f"{start_date or '-'}~{end_date or '-'}",
            operator="covers",
            passed=passed,
            severity="error",
            message="本地行情不能覆盖请求回测区间。",
        )
    ]


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


@lru_cache
def get_market_data_precheck_service() -> MarketDataPrecheckService:
    return MarketDataPrecheckService()
