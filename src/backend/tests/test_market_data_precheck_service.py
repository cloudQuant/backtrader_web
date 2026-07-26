"""Market-data precheck service tests without filesystem or provider coupling."""

from __future__ import annotations

import pytest

from app.schemas.market_data_trust import (
    AssetSpecResponse,
    DataPrecheckRequest,
    MarketDataCoverageResponse,
    MarketDataQualityReportResponse,
)
from app.services.market_data_precheck_service import MarketDataPrecheckService

pytestmark = pytest.mark.asyncio


class _AssetSpecs:
    async def get_or_create(self, **_: object) -> AssetSpecResponse:
        return AssetSpecResponse(
            id="rb0-spec",
            asset_type="futures",
            symbol="RB0",
            exchange="SHFE",
            contract_multiplier=10,
            margin_rate=0.1,
            min_order_size=1,
            commission_rate=0.0001,
        )


class _Coverage:
    def __init__(self, coverage: MarketDataCoverageResponse | None, reports: list[object]) -> None:
        self.coverage = coverage
        self.reports = reports

    async def get_best_coverage(self, **_: object) -> MarketDataCoverageResponse | None:
        return self.coverage

    async def list_quality_reports(self, **_: object) -> list[object]:
        return self.reports


async def test_precheck_passes_with_sufficient_coverage_and_valid_futures_spec():
    service = MarketDataPrecheckService(
        asset_spec_service=_AssetSpecs(),
        coverage_service=_Coverage(
            MarketDataCoverageResponse(
                id="coverage",
                asset_type="futures",
                symbol="RB0",
                timeframe="1h",
                row_count=120,
                missing_ratio=0,
                quality_status="pass",
                start_date="2024-01-01",
                end_date="2024-02-01",
            ),
            [],
        ),
    )

    result = await service.precheck(DataPrecheckRequest(symbol="RB0", timeframe="1h"))

    assert result.passed is True
    assert result.status == "pass"


async def test_precheck_fails_for_blocking_quality_report_and_missing_coverage():
    report = MarketDataQualityReportResponse(
        id="gap",
        asset_type="futures",
        symbol="RB0",
        timeframe="1h",
        provider="local_csv",
        issue_type="futures_night_session_gap",
        severity="error",
        issue_count=1,
    )
    service = MarketDataPrecheckService(
        asset_spec_service=_AssetSpecs(),
        coverage_service=_Coverage(None, [report]),
    )

    result = await service.precheck(DataPrecheckRequest(symbol="RB0", timeframe="1h"))

    assert result.passed is False
    assert result.status == "failed"
    assert "futures_night_session_gap x 1" in result.reasons
    assert any(item.key == "data_coverage_available" for item in result.gate_evaluations)
