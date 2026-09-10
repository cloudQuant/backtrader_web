"""Contracts for the governed legacy K-line response projection."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails
from app.schemas.market_data_platform import MarketDataQueryRequest, ResolvedMarketDataQuery
from app.services.market_data.catalog import DatasetStorageResolution
from app.services.market_data.coverage import (
    CoveragePlan,
    CoverageStatus,
    EventKey,
    ObservationQuality,
    QueryIdentity,
)
from app.services.market_data.identity import ResolvedMarketDataIdentity
from app.services.market_data.legacy_kline_bridge import execute_legacy_kline_local_first
from app.services.market_data.legacy_kline_projection import (
    LegacyKlineBridgeError,
    LegacyKlineInputError,
    parse_legacy_kline_request,
    project_legacy_kline_execution,
)
from app.services.market_data.publication import MarketDataVisibilityAnchor
from app.services.market_data.query_resolution import ResolvedMarketDataQueryContext
from app.services.market_data.query_service import MarketDataQueryExecution
from app.services.market_data.store import LocalObservationRevision

UTC = timezone.utc
NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
CANONICAL_ID = "instrument:stock:CN-SSE:600000"


def _request() -> MarketDataQueryRequest:
    return MarketDataQueryRequest.model_validate(
        {
            "identity": {"canonical_id": CANONICAL_ID},
            "dataset_code": "market.bars",
            "data_kind": "bars",
            "frequency": "1d",
            "start": "2026-09-06T16:00:00+00:00",
            "end": "2026-09-08T16:00:00+00:00",
            "required_fields": ["open", "high", "low", "close", "volume", "change_pct"],
            "adjustment": "qfq",
            "price_basis": "close",
            "currency": "CNY",
            "unit": "share",
            "source_policy_id": "market-default-v1",
            "family_id": "stock.kline_legacy",
            "family_contract_version": "market-data-kline-v1",
            "mode": "local_only",
            "page_size": 2000,
        }
    )


def _execution(
    *,
    observations: tuple[LocalObservationRevision, ...] | None = None,
    expected_event_times: tuple[datetime, ...] | None = None,
    next_cursor: str | None = None,
) -> MarketDataQueryExecution:
    request = _request()
    query = ResolvedMarketDataQuery.from_request(
        request,
        canonical_id=CANONICAL_ID,
        dataset_code="market.bars",
        instrument_metadata_version="stock-v1",
    )
    identity = InstrumentIdentity(
        asset_type="stock",
        identity_level="ASSET",
        canonical_id=CANONICAL_ID,
        display_symbol="600000",
        name="浦发银行",
        venue="CN-SSE",
        currency="CNY",
        timezone="Asia/Shanghai",
        identifier_type="EXCHANGE_SYMBOL",
        identifier_value="600000",
        product_type="EQUITY",
        metadata_version="stock-v1",
        details=StockIdentityDetails(exchange_symbol="600000.SH"),
    )
    context = ResolvedMarketDataQueryContext(
        query=query,
        identity=ResolvedMarketDataIdentity(
            instrument_id="instrument-stock-v1",
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            metadata_version="stock-v1",
            venue="CN-SSE",
            identity=identity,
            valid_from=request.start - timedelta(days=30),
            valid_to=None,
            known_at=request.start - timedelta(days=30),
        ),
        storage=DatasetStorageResolution(
            dataset_id="dataset-market-bars",
            dataset_code="market.bars",
            storage_id="canonical-market-data",
            engine="sqlite",
            database_name="test",
            physical_table="md_observation_revisions",
            write_mode="canonical_read_write",
        ),
        coverage_identity=QueryIdentity(
            dataset_code="market.bars",
            canonical_id=CANONICAL_ID,
            asset_type="stock",
            instrument_metadata_version="stock-v1",
            data_kind="bars",
            market="CN-SSE",
            frequency="1d",
            source_policy_id="market-default-v1",
            adjustment="qfq",
            price_basis="close",
            currency="CNY",
            unit="share",
            family_id="stock.kline_legacy",
            family_contract_version="market-data-kline-v1",
        ),
    )
    event_times = expected_event_times or (request.start, request.start + timedelta(days=1))
    local_rows = observations or tuple(
        LocalObservationRevision(
            revision_id=f"revision-{index}",
            source_snapshot_id=f"snapshot-{index}",
            event_at=event_at,
            available_at=NOW,
            committed_at=NOW,
            visible_at=NOW,
            visibility_sequence=index,
            revision_number=1,
            quality=ObservationQuality.PASS,
            fields=MappingProxyType(
                {
                    "open": "10.005",
                    "high": "11.004",
                    "low": "9.995",
                    "close": "10.505",
                    "volume": "1000",
                    "change_pct": "1.235",
                }
            ),
        )
        for index, event_at in enumerate(event_times, start=1)
    )
    event_keys = tuple(EventKey(event_at) for event_at in event_times)
    anchor = MarketDataVisibilityAnchor(visible_at=NOW, max_visibility_sequence=99)
    return MarketDataQueryExecution(
        context=context,
        knowledge_cutoff=NOW,
        identity_knowledge_cutoff=NOW,
        visibility_anchor=anchor,
        identity_visibility_anchor=anchor,
        coverage=CoveragePlan(
            status=CoverageStatus.COMPLETE,
            expected_event_keys=event_keys,
            accepted_event_keys=event_keys,
            missing_event_keys=(),
            gaps=(),
            rejection_counts={},
        ),
        observations=local_rows,
        next_cursor=next_cursor,
        fetches=(),
        warnings=(),
    )


def test_projection_uses_only_exact_complete_local_event_evidence() -> None:
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    response = project_legacy_kline_execution(_execution(), request=request)

    assert response["symbol"] == "600000"
    assert response["count"] == 2
    assert response["kline"] == {
        "dates": ["2026-09-07", "2026-09-08"],
        "ohlc": [[10.01, 10.51, 10.0, 11.0], [10.01, 10.51, 10.0, 11.0]],
        "volumes": [1000, 1000],
    }
    assert response["records"][0] == {
        "date": "2026-09-07",
        "open": 10.01,
        "high": 11.0,
        "low": 10.0,
        "close": 10.51,
        "volume": 1000,
        "change": 1.24,
    }


@pytest.mark.parametrize("failure", ["extra", "duplicate", "cursor", "field", "volume"])
def test_projection_rejects_non_projectable_local_read(failure: str) -> None:
    execution = _execution()
    if failure == "extra":
        extra = replace(
            execution.observations[0],
            revision_id="extra",
            event_at=datetime(2026, 9, 9, tzinfo=UTC),
        )
        execution = replace(execution, observations=(*execution.observations, extra))
    elif failure == "duplicate":
        duplicate = replace(execution.observations[0], revision_id="duplicate")
        execution = replace(execution, observations=(*execution.observations, duplicate))
    elif failure == "cursor":
        execution = replace(execution, next_cursor="unexpected")
    elif failure == "field":
        invalid = replace(
            execution.observations[0],
            fields=MappingProxyType({**execution.observations[0].fields, "high": float("nan")}),
        )
        execution = replace(execution, observations=(invalid, *execution.observations[1:]))
    elif failure == "volume":
        invalid = replace(
            execution.observations[0],
            fields=MappingProxyType({**execution.observations[0].fields, "volume": "1.5"}),
        )
        execution = replace(execution, observations=(invalid, *execution.observations[1:]))

    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )
    with pytest.raises(LegacyKlineBridgeError):
        project_legacy_kline_execution(execution, request=request)


@pytest.mark.parametrize("failure", ["expected-accepted", "missing", "out-of-window"])
def test_projection_rejects_complete_coverage_with_inconsistent_event_evidence(
    failure: str,
) -> None:
    """`complete` alone cannot authorize a legacy response."""
    execution = _execution()
    coverage = execution.coverage
    if failure == "expected-accepted":
        coverage = replace(coverage, accepted_event_keys=coverage.accepted_event_keys[:1])
    elif failure == "missing":
        coverage = replace(
            coverage,
            missing_event_keys=(coverage.expected_event_keys[0],),
        )
    else:
        outside = EventKey(datetime(2026, 9, 9, tzinfo=UTC))
        coverage = replace(
            coverage,
            expected_event_keys=(outside,),
            accepted_event_keys=(outside,),
        )
    execution = replace(execution, coverage=coverage)
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_COVERAGE_EVENT_INTEGRITY"):
        project_legacy_kline_execution(execution, request=request)


@pytest.mark.parametrize("value", ["1e400", "10000000000000000.01"])
def test_projection_rejects_unrepresentable_legacy_json_numbers(value: str) -> None:
    """A finite Decimal must still survive the legacy JSON-number boundary exactly."""
    execution = _execution()
    invalid = replace(
        execution.observations[0],
        fields=MappingProxyType({**execution.observations[0].fields, "open": value}),
    )
    execution = replace(execution, observations=(invalid, *execution.observations[1:]))
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_FIELD_QUALITY_INVALID"):
        project_legacy_kline_execution(execution, request=request)


@pytest.mark.parametrize(
    ("period", "start_date", "end_date", "frequency", "expected_start", "expected_end"),
    [
        ("daily", "2026-01-01", "2026-01-02", "1d", "2025-12-31T16:00:00+00:00", "2026-01-02T16:00:00+00:00"),
        ("weekly", "2025-12-29", "2026-01-04", "1w", "2025-12-28T16:00:00+00:00", "2026-01-04T16:00:00+00:00"),
        ("monthly", "2026-01-01", "2026-02-28", "1mo", "2025-12-31T16:00:00+00:00", "2026-02-28T16:00:00+00:00"),
    ],
)
def test_request_parser_accepts_only_exact_shanghai_calendar_windows(
    period: str,
    start_date: str,
    end_date: str,
    frequency: str,
    expected_start: str,
    expected_end: str,
) -> None:
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date=start_date,
        end_date=end_date,
        period=period,
    )

    assert request.frequency == frequency
    assert request.start == datetime.fromisoformat(expected_start)
    assert request.end == datetime.fromisoformat(expected_end)


@pytest.mark.parametrize(
    ("start_date", "end_date", "period"),
    [
        ("2026-02-30", "2026-03-01", "daily"),
        ("2026-03-02", "2026-03-01", "daily"),
        ("2026-01-01", "2027-01-02", "daily"),
        ("2026-01-01", "2026-01-04", "weekly"),
        ("2025-12-29", "2026-01-03", "weekly"),
        ("2026-01-02", "2026-01-31", "monthly"),
        ("2026-01-01", "2026-02-27", "monthly"),
        ("2026-01-01", "2026-01-02", "1h"),
        ("0001-01-01", "0001-01-01", "daily"),
        ("9999-12-31", "9999-12-31", "daily"),
        ("0001-01-01", "0001-01-07", "weekly"),
        ("0001-01-01", "0001-01-31", "monthly"),
        ("9999-12-01", "9999-12-31", "monthly"),
    ],
)
def test_request_parser_rejects_invalid_or_oversized_legacy_windows(
    start_date: str,
    end_date: str,
    period: str,
) -> None:
    with pytest.raises(LegacyKlineInputError):
        parse_legacy_kline_request(
            symbol="600000",
            start_date=start_date,
            end_date=end_date,
            period=period,
        )


def test_request_parser_rejects_aligned_weekly_and_monthly_windows_over_the_limit() -> None:
    weekly_start = date(2020, 1, 6)
    weekly_end = weekly_start + timedelta(weeks=261, days=-1)
    monthly_start = date(2020, 1, 1)
    monthly_end = date(2030, 1, 31)

    for start_date, end_date, period in (
        (weekly_start.isoformat(), weekly_end.isoformat(), "weekly"),
        (monthly_start.isoformat(), monthly_end.isoformat(), "monthly"),
    ):
        with pytest.raises(LegacyKlineInputError):
            parse_legacy_kline_request(
                symbol="600000",
                start_date=start_date,
                end_date=end_date,
                period=period,
            )


@pytest.mark.parametrize(
    ("symbol", "period"),
    [
        (" 600000", "daily"),
        ("600000 ", "daily"),
        ("600000", "Daily"),
        ("600000", " daily"),
    ],
)
def test_request_parser_rejects_noncanonical_symbol_and_period_tokens(
    symbol: str,
    period: str,
) -> None:
    with pytest.raises(LegacyKlineInputError):
        parse_legacy_kline_request(
            symbol=symbol,
            start_date="2026-09-07",
            end_date="2026-09-07",
            period=period,
        )


class _ContractResolver:
    async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
        assert symbol == "600000"
        assert period == "daily"
        return {
            "version": "market-data-v2",
            "request": {
                "identity": {"canonical_id": CANONICAL_ID},
                "dataset_code": "market.bars",
                "data_kind": "bars",
                "frequency": "1d",
                "required_fields": ["open", "high", "low", "close", "volume", "change_pct"],
                "adjustment": "qfq",
                "price_basis": "close",
                "currency": "CNY",
                "unit": "share",
                "source_policy_id": "market-default-v1",
                "mode": "local_first",
                "family_id": "stock.kline_legacy",
                "family_contract_version": "market-data-kline-v1",
            },
        }


@pytest.mark.asyncio
async def test_bridge_never_projects_its_first_local_first_execution() -> None:
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )
    final = _execution()
    local_first_calls: list[MarketDataQueryRequest] = []
    local_only_calls: list[MarketDataQueryRequest] = []

    async def execute_local_first(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        local_first_calls.append(query)
        initial = _execution()
        return replace(
            initial,
            context=replace(
                initial.context,
                query=ResolvedMarketDataQuery.from_request(
                    query,
                    canonical_id=CANONICAL_ID,
                    dataset_code="market.bars",
                    instrument_metadata_version="stock-v1",
                ),
            ),
        )

    async def execute_local_only(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        local_only_calls.append(query)
        return final

    response = await execute_legacy_kline_local_first(
        request=request,
        contract_resolver=_ContractResolver(),
        execute_local_first=execute_local_first,
        execute_local_only=execute_local_only,
    )

    assert response["count"] == 2
    assert len(local_first_calls) == len(local_only_calls) == 1
    assert local_first_calls[0].mode == "local_first"
    assert local_first_calls[0].cursor is None
    assert local_first_calls[0].page_size == 2000
    assert local_only_calls[0].mode == "local_only"
    assert local_only_calls[0].cursor is None
    assert local_only_calls[0].page_size == 2000
    assert local_first_calls[0].start == local_only_calls[0].start == request.start
    assert local_first_calls[0].end == local_only_calls[0].end == request.end


@pytest.mark.asyncio
async def test_bridge_preserves_an_exact_frozen_exchange_symbol_alias() -> None:
    """A legacy `.SH` token resolves to the frozen bare provider display symbol."""

    class _ExchangeTokenResolver(_ContractResolver):
        async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
            assert symbol == "600000.SH"
            return await super().resolve_kline_legacy(symbol="600000", period=period)

    request = parse_legacy_kline_request(
        symbol="600000.SH",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )
    local_first_calls: list[MarketDataQueryRequest] = []

    async def execute_local_first(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        local_first_calls.append(query)
        initial = _execution()
        return replace(
            initial,
            context=replace(
                initial.context,
                query=ResolvedMarketDataQuery.from_request(
                    query,
                    canonical_id=CANONICAL_ID,
                    dataset_code="market.bars",
                    instrument_metadata_version="stock-v1",
                ),
            ),
        )

    async def execute_local_only(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        return _execution()

    response = await execute_legacy_kline_local_first(
        request=request,
        contract_resolver=_ExchangeTokenResolver(),
        execute_local_first=execute_local_first,
        execute_local_only=execute_local_only,
    )

    assert response["symbol"] == "600000.SH"
    assert local_first_calls[0].identity.canonical_id == CANONICAL_ID


@pytest.mark.asyncio
async def test_bridge_rejects_a_paginated_first_execution_before_the_reread() -> None:
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )
    local_only_calls = 0

    async def execute_local_first(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        first = _execution(next_cursor="unexpected")
        return replace(
            first,
            context=replace(
                first.context,
                query=ResolvedMarketDataQuery.from_request(
                    query,
                    canonical_id=CANONICAL_ID,
                    dataset_code="market.bars",
                    instrument_metadata_version="stock-v1",
                ),
            ),
        )

    async def execute_local_only(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        nonlocal local_only_calls
        local_only_calls += 1
        return _execution()

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_CURSOR_UNEXPECTED"):
        await execute_legacy_kline_local_first(
            request=request,
            contract_resolver=_ContractResolver(),
            execute_local_first=execute_local_first,
            execute_local_only=execute_local_only,
        )
    assert local_only_calls == 0


@pytest.mark.asyncio
async def test_bridge_rejects_a_private_template_with_non_kline_static_axes() -> None:
    """A compromised resolver cannot redirect the server-owned facade product."""

    class _WrongContractResolver(_ContractResolver):
        async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
            contract = await super().resolve_kline_legacy(symbol=symbol, period=period)
            payload = dict(contract["request"])
            payload["dataset_code"] = "market.stock_daily"
            return {"version": "market-data-v2", "request": payload}

    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    async def unexpected_execution(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        raise AssertionError("invalid private template must not execute")

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_QUERY_CONTRACT_INVALID"):
        await execute_legacy_kline_local_first(
            request=request,
            contract_resolver=_WrongContractResolver(),
            execute_local_first=unexpected_execution,
            execute_local_only=unexpected_execution,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    [
        ("source_policy_id", "other-policy-v1"),
        ("consistency", "strict"),
        ("purpose", "research"),
        ("knowledge_cutoff", "2026-09-08T16:00:00+00:00"),
    ],
)
async def test_bridge_rejects_private_templates_that_drift_from_display_contract(
    field_name: str,
    wrong_value: str,
) -> None:
    """Resolver drift may not change policy, purpose, or PIT semantics before I/O."""

    class _DriftedContractResolver(_ContractResolver):
        async def resolve_kline_legacy(self, *, symbol: str, period: str) -> dict[str, object]:
            contract = await super().resolve_kline_legacy(symbol=symbol, period=period)
            payload = dict(contract["request"])
            payload[field_name] = wrong_value
            return {"version": "market-data-v2", "request": payload}

    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    async def unexpected_execution(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        raise AssertionError("a drifted private template must not execute")

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_QUERY_CONTRACT_INVALID"):
        await execute_legacy_kline_local_first(
            request=request,
            contract_resolver=_DriftedContractResolver(),
            execute_local_first=unexpected_execution,
            execute_local_only=unexpected_execution,
        )


@pytest.mark.asyncio
async def test_bridge_rejects_a_frozen_identity_with_a_different_display_symbol() -> None:
    """The legacy display token must agree exactly with the frozen identity."""
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )
    local_only_calls = 0

    async def execute_local_first(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        initial = _execution()
        resolved = ResolvedMarketDataQuery.from_request(
            query,
            canonical_id=CANONICAL_ID,
            dataset_code="market.bars",
            instrument_metadata_version="stock-v1",
        )
        wrong_display = initial.context.identity.identity.model_copy(
            update={"display_symbol": "600001"}
        )
        return replace(
            initial,
            context=replace(
                initial.context,
                query=resolved,
                identity=replace(initial.context.identity, identity=wrong_display),
            ),
        )

    async def execute_local_only(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        nonlocal local_only_calls
        local_only_calls += 1
        return _execution()

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_QUERY_EXECUTION_INVALID"):
        await execute_legacy_kline_local_first(
            request=request,
            contract_resolver=_ContractResolver(),
            execute_local_first=execute_local_first,
            execute_local_only=execute_local_only,
        )
    assert local_only_calls == 0


@pytest.mark.asyncio
async def test_bridge_rejects_final_reread_with_a_cross_wired_context() -> None:
    """The final local-only result must match every sealed request axis."""
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    async def execute_local_first(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        initial = _execution()
        return replace(
            initial,
            context=replace(
                initial.context,
                query=ResolvedMarketDataQuery.from_request(
                    query,
                    canonical_id=CANONICAL_ID,
                    dataset_code="market.bars",
                    instrument_metadata_version="stock-v1",
                ),
            ),
        )

    async def execute_local_only(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        final = _execution()
        return replace(
            final,
            context=replace(
                final.context,
                query=final.context.query.model_copy(update={"source_policy_id": "other-policy-v1"}),
            ),
        )

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_QUERY_EXECUTION_INVALID"):
        await execute_legacy_kline_local_first(
            request=request,
            contract_resolver=_ContractResolver(),
            execute_local_first=execute_local_first,
            execute_local_only=execute_local_only,
        )


@pytest.mark.asyncio
async def test_bridge_requires_final_reread_to_keep_the_first_frozen_metadata_version() -> None:
    """A self-consistent reread still cannot change the frozen identity revision."""
    request = parse_legacy_kline_request(
        symbol="600000",
        start_date="2026-09-07",
        end_date="2026-09-08",
        period="daily",
    )

    async def execute_local_first(query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        initial = _execution()
        return replace(
            initial,
            context=replace(
                initial.context,
                query=ResolvedMarketDataQuery.from_request(
                    query,
                    canonical_id=CANONICAL_ID,
                    dataset_code="market.bars",
                    instrument_metadata_version="stock-v1",
                ),
            ),
        )

    async def execute_local_only(_query: MarketDataQueryRequest) -> MarketDataQueryExecution:
        final = _execution()
        changed_query = final.context.query.model_copy(
            update={"instrument_metadata_version": "stock-v2"}
        )
        changed_identity = replace(
            final.context.identity,
            metadata_version="stock-v2",
            identity=final.context.identity.identity.model_copy(update={"metadata_version": "stock-v2"}),
        )
        changed_coverage_identity = replace(
            final.context.coverage_identity,
            instrument_metadata_version="stock-v2",
        )
        return replace(
            final,
            context=replace(
                final.context,
                query=changed_query,
                identity=changed_identity,
                coverage_identity=changed_coverage_identity,
            ),
        )

    with pytest.raises(LegacyKlineBridgeError, match="KLINE_REREAD_CONTINUITY_INVALID"):
        await execute_legacy_kline_local_first(
            request=request,
            contract_resolver=_ContractResolver(),
            execute_local_first=execute_local_first,
            execute_local_only=execute_local_only,
        )
