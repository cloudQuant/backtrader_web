"""Offline regression coverage for the reviewed static provider-contract layer."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest

from app.services.market_data.akshare_provider import (
    AKSHARE_ROUTE_REGISTRY,
    AkShareMarketDataProvider,
    AkShareProviderError,
)
from app.services.market_data.dataset_contracts import DEFAULT_DATASET_CONTRACT_REGISTRY
from app.services.market_data.provider_contracts import (
    AKSHARE_PROVIDER_CONTRACT_REGISTRY,
    ProviderContractError,
    ProviderContractRegistry,
)
from app.services.market_data.providers import MarketDataProviderRequest

UTC = timezone.utc


class _TestReceiptRunner:
    """A test-module-only replacement for the private subprocess runner."""

    def __init__(self, callback: Callable[[Mapping[str, object]], Any]) -> None:
        self._callback = callback

    async def execute(
        self,
        envelope: Mapping[str, object],
        *,
        timeout_seconds: float,
    ) -> object:
        del timeout_seconds
        return await self._callback(envelope)


def _test_provider(callback: Callable[[Mapping[str, object]], Any]) -> AkShareMarketDataProvider:
    """Keep offline receipt doubles out of the production constructor API."""
    provider = AkShareMarketDataProvider()
    provider._runner = _TestReceiptRunner(callback)  # type: ignore[assignment]
    return provider


def _request(**changes: object) -> MarketDataProviderRequest:
    values: dict[str, object] = {
        "query_fingerprint": "a" * 64,
        "canonical_id": "instrument:stock:CN-SZSE:000001",
        "asset_type": "stock",
        "provider_symbol": "000001",
        "market": "CN-SZSE",
        "data_kind": "bars",
        "frequency": "1d",
        "start_at": datetime(2026, 1, 2, tzinfo=UTC),
        "end_at": datetime(2026, 1, 4, tzinfo=UTC),
        "required_fields": frozenset({"open", "close"}),
        "provider": "akshare",
        "route_id": "akshare-stock-primary-v1",
        "family_id": "stock.realtime",
        "family_contract_version": "market-data-family-v1",
        "request_id": "A" * 43,
    }
    values.update(changes)
    return MarketDataProviderRequest(**values)  # type: ignore[arg-type]


def test_static_contracts_cover_each_reviewed_akshare_route_and_product_profile() -> None:
    """A route cannot retain a request-time path without one reviewed field profile."""
    route_ids = {route_id for route in AKSHARE_ROUTE_REGISTRY for route_id in route.route_ids}
    contract_route_ids = {
        contract.route_id for contract in AKSHARE_PROVIDER_CONTRACT_REGISTRY.contracts
    }

    assert contract_route_ids == route_ids
    for contract in AKSHARE_PROVIDER_CONTRACT_REGISTRY.contracts:
        family = DEFAULT_DATASET_CONTRACT_REGISTRY.ready_contract_for(
            family_id=contract.family_id,
            asset_type=contract.asset_type,
        )
        assert contract.family_contract_version == family.family_contract_version
        assert contract.field_profile.profile_id == family.field_profile.profile_id
        assert contract.field_profile.required_fields == family.field_profile.required_fields
        assert contract.field_profile.optional_fields == family.field_profile.optional_fields


def test_contract_descriptor_and_summary_are_stable_across_registry_rebuilds() -> None:
    """Contract evidence is canonical and cannot be relabeled with another digest."""
    first = AKSHARE_PROVIDER_CONTRACT_REGISTRY.contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )
    rebuilt = ProviderContractRegistry(AKSHARE_PROVIDER_CONTRACT_REGISTRY.contracts).contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )

    assert first.descriptor_sha256 == rebuilt.descriptor_sha256
    assert dict(first.summary) == dict(rebuilt.summary)
    assert json.dumps(dict(first.summary), sort_keys=True, separators=(",", ":")) == json.dumps(
        dict(rebuilt.summary),
        sort_keys=True,
        separators=(",", ":"),
    )
    assert first.descriptor["descriptor_sha256"] == first.descriptor_sha256

    with pytest.raises(ProviderContractError) as mismatch:
        replace(first, descriptor_sha256="0" * 64)

    assert mismatch.value.code == "PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH"


def test_contract_query_transform_preserves_reviewed_half_open_window_semantics() -> None:
    """The static transform turns a UTC half-open query into AkShare's inclusive date API."""
    contract = AKSHARE_PROVIDER_CONTRACT_REGISTRY.select_for_request(_request())

    prepared = contract.prepare_akshare_request(_request())

    assert prepared.endpoint == "stock_zh_a_hist"
    assert dict(prepared.call_kwargs) == {
        "symbol": "000001",
        "period": "daily",
        "start_date": "20260102",
        "end_date": "20260103",
        "adjust": "",
    }
    assert prepared.descriptor_sha256 == contract.descriptor_sha256
    assert contract.summary["window_semantics"] == "utc-half-open-window-v1"


def test_contract_profile_maps_reviewed_fields_and_rejects_an_unmapped_required_field() -> None:
    """A normalizer's aliases cannot be widened by a caller-provided required field."""
    contract = AKSHARE_PROVIDER_CONTRACT_REGISTRY.select_for_request(_request())

    assert contract.normalized_field_name("开盘") == "open"
    assert contract.normalized_field_name("收盘") == "close"
    assert set(contract.field_profile.required_fields) <= contract.field_profile.mapped_fields

    with pytest.raises(ProviderContractError) as missing:
        AKSHARE_PROVIDER_CONTRACT_REGISTRY.select_for_request(
            _request(required_fields=frozenset({"close", "unreviewed_metric"}))
        )

    assert missing.value.code == "PROVIDER_CONTRACT_FIELD_MAPPING_MISSING"
    assert missing.value.detail == "unreviewed_metric"


@pytest.mark.asyncio
async def test_adapter_rejects_unknown_route_and_missing_mapping_before_provider_io() -> None:
    """No fake runner receipt is requested for rejected static contracts."""
    calls: list[str] = []

    async def runner(_: Mapping[str, object]) -> dict[str, object]:
        calls.append("runner")
        pytest.fail("runner must not run for a rejected contract")

    provider = _test_provider(runner)

    with pytest.raises(AkShareProviderError) as unknown:
        await provider.fetch(_request(route_id="akshare-stock-unreviewed-v1"))

    assert unknown.value.code == "AKSHARE_ROUTE_UNSUPPORTED"
    assert calls == []

    with pytest.raises(AkShareProviderError) as unmapped:
        await provider.fetch(_request(required_fields=frozenset({"unreviewed_metric"})))

    assert unmapped.value.code == "AKSHARE_PROVIDER_CONTRACT_FIELD_MAPPING_MISSING"
    assert calls == []


def _tampered_stock_contract_registry() -> ProviderContractRegistry:
    """Build a self-consistent but unreviewed field-map widening for a negative test."""
    reviewed = AKSHARE_PROVIDER_CONTRACT_REGISTRY.contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )
    widened_profile = replace(
        reviewed.field_profile,
        mapped_fields=reviewed.field_profile.mapped_fields | {"unreviewed_metric"},
    )
    widened_contract = replace(
        reviewed,
        field_profile=widened_profile,
        response_field_aliases={
            **dict(reviewed.response_field_aliases),
            "未审核指标": "unreviewed_metric",
        },
        descriptor_sha256=None,
    )

    assert widened_contract.descriptor_sha256 != reviewed.descriptor_sha256
    return ProviderContractRegistry((widened_contract,))


def _digest_spoofed_stock_contract_registry() -> ProviderContractRegistry:
    """Spoof the reviewed digest after registry validation to model unsafe mutation."""
    registry = _tampered_stock_contract_registry()
    spoofed = registry.contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )
    reviewed = AKSHARE_PROVIDER_CONTRACT_REGISTRY.contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )
    object.__setattr__(spoofed, "descriptor_sha256", reviewed.descriptor_sha256)
    return registry


def test_adapter_has_no_runtime_contract_registry_injection_seam() -> None:
    """A caller cannot replace reviewed contracts during adapter construction."""
    with pytest.raises(TypeError, match="contracts"):
        AkShareMarketDataProvider(
            contracts=_tampered_stock_contract_registry(),  # type: ignore[call-arg]
        )


@pytest.mark.asyncio
async def test_adapter_ignores_digest_spoofed_private_registry_before_provider_io() -> None:
    """A spoofed private registry cannot replace the import-time reviewed table."""
    runner_calls: list[str] = []

    async def runner(_: Mapping[str, object]) -> dict[str, object]:
        runner_calls.append("runner")
        pytest.fail("runner must not run for a rejected contract")

    provider = _test_provider(runner)
    # The public constructor has no registry seam. This unsafe in-process
    # attribute replacement must be ignored by the import-time selector.
    provider._contracts = _digest_spoofed_stock_contract_registry()

    with pytest.raises(AkShareProviderError) as unmapped:
        await provider.fetch(_request(required_fields=frozenset({"unreviewed_metric"})))

    assert unmapped.value.code == "AKSHARE_PROVIDER_CONTRACT_FIELD_MAPPING_MISSING"
    assert runner_calls == []


@pytest.mark.asyncio
async def test_adapter_rejects_postconstruction_reviewed_contract_mutation_before_provider_io() -> (
    None
):
    """The selected reviewed object must still match its import-time descriptor digest."""
    runner_calls: list[str] = []

    async def runner(_: Mapping[str, object]) -> dict[str, object]:
        runner_calls.append("runner")
        pytest.fail("runner must not run for a mutated contract")

    reviewed = AKSHARE_PROVIDER_CONTRACT_REGISTRY.contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )
    original_profile = reviewed.field_profile
    original_aliases = reviewed.response_field_aliases
    original_digest = reviewed.descriptor_sha256
    widened_profile = replace(
        reviewed.field_profile,
        mapped_fields=reviewed.field_profile.mapped_fields | {"unreviewed_metric"},
    )
    provider = _test_provider(runner)

    try:
        object.__setattr__(reviewed, "field_profile", widened_profile)
        object.__setattr__(
            reviewed,
            "response_field_aliases",
            {**dict(reviewed.response_field_aliases), "未审核指标": "unreviewed_metric"},
        )
        object.__setattr__(reviewed, "descriptor_sha256", original_digest)

        with pytest.raises(AkShareProviderError) as mismatch:
            await provider.fetch(_request(required_fields=frozenset({"unreviewed_metric"})))
    finally:
        object.__setattr__(reviewed, "field_profile", original_profile)
        object.__setattr__(reviewed, "response_field_aliases", original_aliases)
        object.__setattr__(reviewed, "descriptor_sha256", original_digest)

    reviewed.assert_descriptor_integrity()
    assert mismatch.value.code == "AKSHARE_PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH"
    assert runner_calls == []


@pytest.mark.asyncio
async def test_adapter_rechecks_reviewed_contract_integrity_after_runner_receipt() -> None:
    """A mutation during child execution cannot alter normalization after I/O."""
    reviewed = AKSHARE_PROVIDER_CONTRACT_REGISTRY.contract_for(
        provider="akshare",
        route_id="akshare-stock-primary-v1",
    )
    original_profile = reviewed.field_profile
    widened_profile = replace(
        reviewed.field_profile,
        mapped_fields=reviewed.field_profile.mapped_fields | {"unreviewed_metric"},
    )
    runner_calls: list[str] = []

    async def runner(envelope: Mapping[str, object]) -> dict[str, object]:
        execution = envelope["execution"]
        assert isinstance(execution, Mapping)
        runner_calls.append("runner")
        object.__setattr__(reviewed, "field_profile", widened_profile)
        return {
            "protocol_version": "akshare-market-data-v1",
            "request_id": envelope["request_id"],
            "request": envelope["request"],
            "execution": execution,
            "source_revision": execution["source_revision"],
            "response_rows": [
                {"日期": "2026-01-02", "股票代码": "000001", "开盘": 10.0, "收盘": 10.5}
            ],
        }

    provider = _test_provider(runner)
    try:
        with pytest.raises(AkShareProviderError) as mismatch:
            await provider.fetch(_request())
    finally:
        object.__setattr__(reviewed, "field_profile", original_profile)

    reviewed.assert_descriptor_integrity()
    assert mismatch.value.code == "AKSHARE_PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH"
    assert runner_calls == ["runner"]


@pytest.mark.asyncio
async def test_adapter_rejects_provider_endpoint_descriptor_drift_before_provider_io() -> None:
    """The server-owned dispatch token must agree with the selected static contract."""
    calls: list[str] = []

    async def runner(_: Mapping[str, object]) -> dict[str, object]:
        calls.append("runner")
        pytest.fail("descriptor mismatch must not invoke the runner")

    provider = _test_provider(runner)

    with pytest.raises(AkShareProviderError) as mismatch:
        await provider.fetch(_request(provider_endpoint="fund_etf_hist_em"))

    assert mismatch.value.code == "AKSHARE_PROVIDER_CONTRACT_DESCRIPTOR_MISMATCH"
    assert calls == []


def test_contract_requires_the_exact_route_family_and_revision_pair() -> None:
    """A same-shaped sibling family cannot select the stock realtime source contract."""
    with pytest.raises(ProviderContractError) as mismatch:
        AKSHARE_PROVIDER_CONTRACT_REGISTRY.select_for_request(
            _request(
                route_id="akshare-stock-primary-v1",
                family_id="stock.kline_legacy",
                family_contract_version="market-data-kline-v1",
            )
        )

    assert mismatch.value.code == "PROVIDER_CONTRACT_FAMILY_MISMATCH"
