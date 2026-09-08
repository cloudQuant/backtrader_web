"""Contracts for the offline-only AkShare full-market snapshot normalizer."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from unittest.mock import Mock

import pytest

from app.services.market_data.providers import ProviderMarketObservation
from app.services.market_data.snapshot_importer import (
    AkShareSnapshotImporter,
    AkShareSnapshotImportError,
    FrozenSnapshotIdentity,
    SnapshotImportResult,
)

UTC = timezone.utc


def _identity(
    *,
    asset_type: str = "stock",
    provider_symbol: str = "000001",
    canonical_id: str = "instrument:stock:CN-SZSE:000001",
    market: str = "CN-SZSE",
    provider_market: str | None = None,
) -> FrozenSnapshotIdentity:
    """Build one frozen identity with deliberately explicit source dimensions."""
    return FrozenSnapshotIdentity(
        canonical_id=canonical_id,
        asset_type=asset_type,
        provider_symbol=provider_symbol,
        market=market,
        provider_market=provider_market,
    )


def _import(
    *,
    rows: list[dict[str, object]],
    identities: list[FrozenSnapshotIdentity] | None = None,
    asset_type: str = "stock",
    required_fields: frozenset[str] = frozenset({"price"}),
    mode: Literal["schedule", "shadow"] = "schedule",
    time_basis: Literal["source_row", "collector_observed"] = "source_row",
    collected_at: datetime | None = None,
) -> SnapshotImportResult:
    """Invoke the pure importer with a fixed, local-only batch shape."""
    return AkShareSnapshotImporter(mode=mode).import_rows(
        asset_type=asset_type,
        rows=rows,
        frozen_identities=identities or [_identity(asset_type=asset_type)],
        required_fields=required_fields,
        time_basis=time_basis,
        collected_at=collected_at,
    )


@pytest.mark.parametrize("mode", ("schedule", "shadow"))
def test_schedule_or_shadow_importer_normalizes_one_exact_source_row_without_a_fetch_route(
    mode: Literal["schedule", "shadow"],
) -> None:
    """A mocked collector row becomes a standard observation only after exact matching."""
    source_rows = Mock(
        return_value=[
            {
                "代码": "000001",
                "更新时间": "2026-09-08 09:30:00",
                "名称": "平安银行",
                "最新价": 10.5,
                "成交量": 1000,
            }
        ]
    )
    importer = AkShareSnapshotImporter(mode=mode)

    result = importer.import_rows(
        asset_type="stock",
        rows=source_rows(),
        frozen_identities=[_identity()],
        required_fields=frozenset({"price", "volume"}),
    )

    source_rows.assert_called_once_with()
    assert not hasattr(importer, "fetch")
    assert result.mode == mode
    assert len(result.imported) == 1
    normalized = result.imported[0]
    assert isinstance(normalized.observation, ProviderMarketObservation)
    assert normalized.observation.event_at == datetime(2026, 9, 8, 1, 30, tzinfo=UTC)
    assert normalized.observation.available_at == datetime(2026, 9, 8, 1, 30, tzinfo=UTC)
    assert normalized.observation.fields == {"price": 10.5, "volume": 1000}
    assert "名称" not in normalized.observation.fields
    assert result.observations == (normalized.observation,)
    assert result.provenance_rows == (
        {
            "canonical_id": "instrument:stock:CN-SZSE:000001",
            "asset_type": "stock",
            "provider_symbol": "000001",
            "market": "CN-SZSE",
            "provider_market": None,
            "source_event_time": "2026-09-08T01:30:00+00:00",
            "time_basis": "source_row",
            "collector_observed_at": None,
        },
    )


@pytest.mark.parametrize(
    ("row", "expected_code"),
    [
        (
            {"代码": "000002", "更新时间": "2026-09-08 09:30:00", "最新价": 10.5},
            "AKSHARE_SNAPSHOT_IDENTITY_UNMATCHED",
        ),
        (
            {
                "代码": "000001",
                "symbol": "000002",
                "更新时间": "2026-09-08 09:30:00",
                "最新价": 10.5,
            },
            "AKSHARE_SNAPSHOT_IDENTITY_AMBIGUOUS",
        ),
    ],
)
def test_snapshot_importer_rejects_unmatched_or_ambiguous_returned_identity(
    row: dict[str, object],
    expected_code: str,
) -> None:
    """Neither a nearby symbol nor conflicting returned aliases can select an identity."""
    with pytest.raises(AkShareSnapshotImportError) as rejected:
        _import(rows=[row])

    assert rejected.value.code == expected_code


def test_snapshot_importer_rejects_duplicate_rows_for_one_frozen_identity() -> None:
    """One captured batch cannot silently overwrite an earlier row for the same instrument."""
    with pytest.raises(AkShareSnapshotImportError) as duplicate:
        _import(
            rows=[
                {"代码": "000001", "更新时间": "2026-09-08 09:30:00", "最新价": 10.5},
                {"代码": "000001", "更新时间": "2026-09-08 09:31:00", "最新价": 10.6},
            ]
        )

    assert duplicate.value.code == "AKSHARE_SNAPSHOT_ROW_DUPLICATE"


def test_snapshot_importer_requires_a_parseable_source_row_timestamp_by_default() -> None:
    """A broad response with no row-owned instant is not a provider tick by default."""
    with pytest.raises(AkShareSnapshotImportError) as missing_time:
        _import(rows=[{"代码": "000001", "最新价": 10.5}])

    assert missing_time.value.code == "AKSHARE_SNAPSHOT_TIMESTAMP_MISSING"


@pytest.mark.parametrize(
    ("source_time", "expected_code"),
    [
        ("--", "AKSHARE_SNAPSHOT_TIMESTAMP_INVALID"),
        ("N/A", "AKSHARE_SNAPSHOT_TIMESTAMP_INVALID"),
        ("   ", "AKSHARE_SNAPSHOT_TIMESTAMP_MISSING"),
        (date(2026, 9, 8), "AKSHARE_SNAPSHOT_TIMESTAMP_INVALID"),
    ],
)
def test_snapshot_importer_rejects_unavailable_or_date_only_declared_source_timestamps(
    source_time: object,
    expected_code: str,
) -> None:
    """Timestamp columns remain strict rather than becoming JSON strings."""
    with pytest.raises(AkShareSnapshotImportError) as rejected:
        _import(rows=[{"代码": "000001", "更新时间": source_time, "最新价": 10.5}])

    assert rejected.value.code == expected_code


def test_snapshot_importer_rejects_missing_or_undeclared_required_fields() -> None:
    """Absent and undeclared source values cannot satisfy a normalized field profile."""
    row = {"代码": "000001", "更新时间": "2026-09-08 09:30:00", "最新价": None}

    with pytest.raises(AkShareSnapshotImportError) as unavailable:
        _import(rows=[row])
    with pytest.raises(AkShareSnapshotImportError) as unsupported:
        _import(rows=[row], required_fields=frozenset({"synthetic_field"}))

    assert unavailable.value.code == "AKSHARE_SNAPSHOT_REQUIRED_FIELDS_MISSING"
    assert unavailable.value.detail == "price"
    assert unsupported.value.code == "AKSHARE_SNAPSHOT_REQUIRED_FIELDS_UNSUPPORTED"


@pytest.mark.parametrize(
    "raw_value",
    [
        "--",
        "N/A",
        "   ",
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_snapshot_importer_rejects_invalid_values_for_declared_numeric_fields(
    raw_value: object,
) -> None:
    """Declared quote metrics cannot preserve provider placeholders as data."""
    with pytest.raises(AkShareSnapshotImportError) as rejected:
        _import(
            rows=[
                {
                    "代码": "000001",
                    "更新时间": "2026-09-08 09:30:00",
                    "最新价": raw_value,
                }
            ]
        )

    assert rejected.value.code == "AKSHARE_SNAPSHOT_FIELD_VALUE_INVALID"
    assert rejected.value.detail == "price"


@pytest.mark.parametrize(
    ("raw_value", "expected_price"),
    [
        (" 10.50 ", "10.50"),
        (Decimal("12.34"), "12.34"),
    ],
)
def test_snapshot_importer_normalizes_numeric_strings_and_decimals_for_json_storage(
    raw_value: object,
    expected_price: str,
) -> None:
    """Accepted schema metrics become finite JSON numbers before persistence."""
    result = _import(
        rows=[
            {
                "代码": "000001",
                "更新时间": "2026-09-08 09:30:00",
                "最新价": raw_value,
            }
        ]
    )

    fields = result.observations[0].fields
    assert fields == {"price": expected_price}
    assert isinstance(fields["price"], str)
    assert json.loads(json.dumps(dict(fields))) == {"price": expected_price}


def test_stock_collector_observed_requires_a_caller_audit_time_and_discloses_its_basis() -> None:
    """Wide stock rows may use collection time only when the caller explicitly supplies it."""
    collected_at = datetime(2026, 9, 8, 1, 35, tzinfo=UTC)
    result = _import(
        rows=[{"代码": "000001", "最新价": 10.5}],
        time_basis="collector_observed",
        collected_at=collected_at,
    )

    normalized = result.imported[0]
    assert normalized.source_event_time is None
    assert normalized.time_basis == "collector_observed"
    assert normalized.observation.event_at == collected_at
    assert normalized.observation.available_at == collected_at
    assert result.provenance_rows[0]["source_event_time"] is None
    assert result.provenance_rows[0]["time_basis"] == "collector_observed"
    assert result.provenance_rows[0]["collector_observed_at"] == collected_at.isoformat()

    with pytest.raises(AkShareSnapshotImportError) as omitted_audit_time:
        _import(rows=[{"代码": "000001", "最新价": 10.5}], time_basis="collector_observed")
    with pytest.raises(AkShareSnapshotImportError) as source_time_conflict:
        _import(
            rows=[{"代码": "000001", "更新时间": "2026-09-08 09:30:00", "最新价": 10.5}],
            time_basis="collector_observed",
            collected_at=collected_at,
        )

    assert omitted_audit_time.value.code == "AKSHARE_SNAPSHOT_COLLECTED_AT_REQUIRED"
    assert source_time_conflict.value.code == "AKSHARE_SNAPSHOT_TIME_BASIS_CONFLICT"


@pytest.mark.parametrize(
    ("asset_type", "identity", "row"),
    [
        (
            "fx",
            _identity(
                asset_type="fx",
                provider_symbol="USDCNY",
                canonical_id="instrument:fx:OTC:USDCNY",
                market="OTC",
            ),
            {"代码": "USDCNY", "最新价": 7.1},
        ),
        (
            "option",
            _identity(
                asset_type="option",
                provider_symbol="MO2609-P-5000",
                canonical_id="instrument:option:CFFEX:MO2609-P-5000",
                market="CFFEX",
                provider_market="CFFEX",
            ),
            {"市场标识": "CFFEX", "代码": "MO2609-P-5000", "最新价": 102.5},
        ),
    ],
)
def test_collector_observed_is_explicitly_supported_for_fx_and_option_wide_rows(
    asset_type: str,
    identity: FrozenSnapshotIdentity,
    row: dict[str, object],
) -> None:
    """Only schemas explicitly opting in can represent a missing row time as collection time."""
    result = _import(
        asset_type=asset_type,
        identities=[identity],
        rows=[row],
        time_basis="collector_observed",
        collected_at=datetime(2026, 9, 8, 1, 35, tzinfo=UTC),
    )

    assert result.imported[0].source_event_time is None
    assert result.provenance_rows[0]["time_basis"] == "collector_observed"


def test_collector_observed_is_rejected_for_fund_rows_that_need_source_time() -> None:
    """ETF/fund imports cannot turn a missing upstream timestamp into a local provider fact."""
    fund_identity = _identity(
        asset_type="fund",
        provider_symbol="510300",
        canonical_id="instrument:fund:CN-SSE:510300",
        market="CN-SSE",
    )

    with pytest.raises(AkShareSnapshotImportError) as rejected:
        _import(
            asset_type="fund",
            identities=[fund_identity],
            rows=[{"基金代码": "510300", "最新价": 4.2}],
            time_basis="collector_observed",
            collected_at=datetime(2026, 9, 8, 1, 35, tzinfo=UTC),
        )

    assert rejected.value.code == "AKSHARE_SNAPSHOT_COLLECTOR_TIME_UNSUPPORTED"


def test_crypto_import_requires_exact_frozen_market_and_pair_identity() -> None:
    """A crypto pair is never accepted without the source venue dimension that scopes it."""
    identity = _identity(
        asset_type="crypto",
        provider_symbol="BTC/USDT",
        canonical_id="instrument:crypto:BINANCE:BTC-USDT:spot",
        market="BINANCE",
        provider_market="Binance",
    )
    row = {
        "市场": "Binance",
        "交易品种": "BTC/USDT",
        "更新时间": "2026-09-08T09:30:00+00:00",
        "最近报价": 64_000.0,
    }

    result = _import(asset_type="crypto", identities=[identity], rows=[row])
    assert result.observations[0].fields == {"price": 64_000.0}
    assert result.provenance_rows[0]["provider_market"] == "Binance"

    with pytest.raises(AkShareSnapshotImportError) as mismatch:
        _import(
            asset_type="crypto",
            identities=[identity],
            rows=[{**row, "市场": "OtherExchange"}],
        )
    with pytest.raises(AkShareSnapshotImportError) as unscoped_identity:
        _import(
            asset_type="crypto",
            identities=[
                _identity(
                    asset_type="crypto",
                    provider_symbol="BTC/USDT",
                    canonical_id="instrument:crypto:BINANCE:BTC-USDT:spot",
                    market="BINANCE",
                )
            ],
            rows=[row],
        )

    assert mismatch.value.code == "AKSHARE_SNAPSHOT_IDENTITY_UNMATCHED"
    assert unscoped_identity.value.code == "AKSHARE_SNAPSHOT_IDENTITY_PROVIDER_MARKET_MISSING"
