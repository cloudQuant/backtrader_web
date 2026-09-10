"""Server-owned local-first orchestration for the legacy K-line facade."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from app.schemas.market_data_platform import MarketDataQueryRequest
from app.services.market_data.dataset_contracts import (
    KLINE_LEGACY_CONTRACT_VERSION,
    KLINE_LEGACY_FAMILY_ID,
)
from app.services.market_data.legacy_kline_identity import matches_legacy_kline_display_token
from app.services.market_data.legacy_kline_projection import (
    LegacyKlineBridgeError,
    LegacyKlineRequest,
    project_legacy_kline_execution,
)
from app.services.market_data.query_service import MarketDataQueryExecution

_LEGACY_KLINE_PAGE_SIZE = 2000


class _LegacyKlineContractResolver(Protocol):
    async def resolve_kline_legacy(
        self,
        *,
        symbol: str,
        period: str,
    ) -> dict[str, Any] | None:
        """Return the private fixed v2 template for one exact legacy selection."""


async def execute_legacy_kline_local_first(
    *,
    request: LegacyKlineRequest,
    contract_resolver: _LegacyKlineContractResolver,
    execute_local_first: Callable[[MarketDataQueryRequest], Awaitable[MarketDataQueryExecution]],
    execute_local_only: Callable[[MarketDataQueryRequest], Awaitable[MarketDataQueryExecution]],
) -> dict[str, Any]:
    """Fill a governed local-first gap, then project only a local-only reread.

    The two execution callables deliberately make the required persistence
    boundary explicit.  The first can perform provider I/O and receipt
    publication through the normal query service; the second is always a
    fresh ``local_only`` request whose typed result is the sole projection
    input.
    """
    if not isinstance(request, LegacyKlineRequest):
        raise TypeError("request must be a LegacyKlineRequest")
    contract = await contract_resolver.resolve_kline_legacy(
        symbol=request.symbol,
        period=request.period,
    )
    local_first_request = _request_from_private_contract(contract, request=request)
    initial = await execute_local_first(local_first_request)
    _assert_execution_context(
        initial,
        request=local_first_request,
        legacy_request=request,
        expected_mode="local_first",
    )
    if initial.next_cursor is not None:
        raise LegacyKlineBridgeError("KLINE_CURSOR_UNEXPECTED")

    local_only_request = local_first_request.model_copy(
        update={"mode": "local_only", "cursor": None, "page_size": _LEGACY_KLINE_PAGE_SIZE}
    )
    final = await execute_local_only(local_only_request)
    _assert_execution_context(
        final,
        request=local_only_request,
        legacy_request=request,
        expected_mode="local_only",
    )
    _assert_reread_continuity(initial=initial, final=final)
    return project_legacy_kline_execution(final, request=request)


def _request_from_private_contract(
    contract: object,
    *,
    request: LegacyKlineRequest,
) -> MarketDataQueryRequest:
    """Seal the legacy time window onto the fixed server-issued K-line template."""
    if not isinstance(contract, Mapping) or set(contract) != {"version", "request"}:
        raise LegacyKlineBridgeError("KLINE_CONTRACT_UNAVAILABLE")
    if contract.get("version") != "market-data-v2" or not isinstance(contract.get("request"), Mapping):
        raise LegacyKlineBridgeError("KLINE_CONTRACT_UNAVAILABLE")
    payload = dict(contract["request"])
    payload.update(
        {
            "start": request.start,
            "end": request.end,
            "mode": "local_first",
            "cursor": None,
            "page_size": _LEGACY_KLINE_PAGE_SIZE,
        }
    )
    try:
        query = MarketDataQueryRequest.model_validate(payload)
    except ValidationError as exc:
        raise LegacyKlineBridgeError("KLINE_QUERY_CONTRACT_INVALID") from exc
    if (
        query.identity.canonical_id is None
        or query.dataset_code != "market.bars"
        or query.data_kind != "bars"
        or query.frequency != request.frequency
        or query.required_fields
        != ("change_pct", "close", "high", "low", "open", "volume")
        or query.adjustment != "qfq"
        or query.price_basis != "close"
        or query.currency != "CNY"
        or query.unit != "share"
        or query.source_policy_id != "market-default-v1"
        or query.family_id != KLINE_LEGACY_FAMILY_ID
        or query.family_contract_version != KLINE_LEGACY_CONTRACT_VERSION
        or query.consistency != "display"
        or query.purpose != "display"
        or query.knowledge_cutoff is not None
        or query.mode != "local_first"
        or query.cursor is not None
        or query.page_size != _LEGACY_KLINE_PAGE_SIZE
    ):
        raise LegacyKlineBridgeError("KLINE_QUERY_CONTRACT_INVALID")
    return query


def _assert_execution_context(
    execution: object,
    *,
    request: MarketDataQueryRequest,
    legacy_request: LegacyKlineRequest,
    expected_mode: str,
) -> None:
    """Reject any execution that is not the exact sealed K-line request."""
    if not isinstance(execution, MarketDataQueryExecution):
        raise LegacyKlineBridgeError("KLINE_QUERY_EXECUTION_INVALID")
    query = execution.context.query
    if (
        query.mode != expected_mode
        or query.identity != request.identity
        or query.canonical_id != request.identity.canonical_id
        or query.dataset_code != request.dataset_code
        or query.data_kind != request.data_kind
        or query.frequency != request.frequency
        or query.start != request.start
        or query.end != request.end
        or query.required_fields != request.required_fields
        or query.family_id != request.family_id
        or query.family_contract_version != request.family_contract_version
        or query.source_policy_id != request.source_policy_id
        or query.adjustment != request.adjustment
        or query.price_basis != request.price_basis
        or query.currency != request.currency
        or query.unit != request.unit
        or query.consistency != request.consistency
        or query.purpose != request.purpose
        or query.knowledge_cutoff != request.knowledge_cutoff
        or query.page_size != request.page_size
        or query.cursor != request.cursor
        or execution.context.identity.canonical_id != query.canonical_id
        or execution.context.identity.metadata_version != query.instrument_metadata_version
        or not matches_legacy_kline_display_token(
            execution.context.identity.identity,
            token=legacy_request.symbol,
        )
        or execution.context.coverage_identity.canonical_id != query.canonical_id
        or execution.context.coverage_identity.instrument_metadata_version
        != query.instrument_metadata_version
        or execution.context.coverage_identity.dataset_code != query.dataset_code
        or execution.context.coverage_identity.data_kind != query.data_kind
        or execution.context.coverage_identity.frequency != query.frequency
        or execution.context.coverage_identity.source_policy_id != query.source_policy_id
        or execution.context.coverage_identity.adjustment != query.adjustment
        or execution.context.coverage_identity.price_basis != query.price_basis
        or execution.context.coverage_identity.currency != query.currency
        or execution.context.coverage_identity.unit != query.unit
        or execution.context.coverage_identity.family_id != query.family_id
        or execution.context.coverage_identity.family_contract_version
        != query.family_contract_version
    ):
        raise LegacyKlineBridgeError("KLINE_QUERY_EXECUTION_INVALID")


def _assert_reread_continuity(
    *,
    initial: MarketDataQueryExecution,
    final: MarketDataQueryExecution,
) -> None:
    """Require the local reread to keep the first execution's frozen identity."""
    initial_query = initial.context.query
    final_query = final.context.query
    if (
        final_query.canonical_id != initial_query.canonical_id
        or final_query.instrument_metadata_version != initial_query.instrument_metadata_version
        or final.context.identity.canonical_id != initial.context.identity.canonical_id
        or final.context.identity.metadata_version != initial.context.identity.metadata_version
        or final.context.coverage_identity != initial.context.coverage_identity
    ):
        raise LegacyKlineBridgeError("KLINE_REREAD_CONTINUITY_INVALID")


__all__ = ["execute_legacy_kline_local_first"]
