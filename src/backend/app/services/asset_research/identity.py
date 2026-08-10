"""Strict conversion from market-search candidates to canonical identities."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import ValidationError

from app.schemas.asset_research import (
    IdentityLevel,
    InstrumentIdentity,
    InstrumentResolveRequest,
    PublicAssetType,
)


class MarketInstrumentLookup(Protocol):
    """The restricted discovery surface used by the identity layer."""

    async def list_instruments(
        self,
        *,
        asset_type: PublicAssetType,
        search: str = "",
        limit: int = 80,
    ) -> dict[str, Any]: ...


class InstrumentResolutionError(ValueError):
    """Stable user-safe code for a failed or ambiguous canonical identity lookup."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _normalized(value: str) -> str:
    return re.sub(r"[\s._:/-]+", "", value).upper()


class InstrumentResolver:
    """Reject ambiguous/weak discovery results before they enter research storage."""

    def __init__(self, market_instruments: MarketInstrumentLookup) -> None:
        self._market_instruments = market_instruments

    async def resolve(self, request: InstrumentResolveRequest) -> InstrumentIdentity:
        """Resolve an exact market option; never substitute a recent arbitrary sample."""
        payload = await self._market_instruments.list_instruments(
            asset_type=request.asset_type,
            search=request.query,
            limit=20,
        )
        items = [item for item in payload.get("items", []) if isinstance(item, dict)]
        exact_candidates, discovery_candidates = self._filter_candidates(items, request)
        if len(exact_candidates) == 1:
            return self._build_identity(request.asset_type, exact_candidates[0])
        if len(exact_candidates) > 1 or len(discovery_candidates) > 1:
            raise InstrumentResolutionError("INSTRUMENT_AMBIGUOUS")
        raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED")

    async def search(
        self,
        *,
        asset_type: PublicAssetType,
        query: str,
        limit: int,
        identity_level: IdentityLevel | None = None,
    ) -> list[dict[str, Any]]:
        """Return raw discovery candidates without silently confirming an identity."""
        payload = await self._market_instruments.list_instruments(
            asset_type=asset_type,
            search=query,
            limit=limit,
        )
        items = [item for item in payload.get("items", []) if isinstance(item, dict)]
        if identity_level is None:
            return items
        return [
            item
            for item in items
            if self._candidate_identity_level(item) == identity_level
        ]

    @staticmethod
    def _filter_candidates(
        items: list[dict[str, Any]], request: InstrumentResolveRequest
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        exact_query = _normalized(request.query)
        seen: set[tuple[str, str]] = set()
        exact: list[dict[str, Any]] = []
        name_exact: list[dict[str, Any]] = []
        discovery_candidates: list[dict[str, Any]] = []
        for item in items:
            if item.get("asset_type") != request.asset_type:
                continue
            if (
                request.identity_level is not None
                and InstrumentResolver._candidate_identity_level(item) != request.identity_level
            ):
                continue
            symbol = str(item.get("symbol") or "").strip()
            market = str(item.get("market") or "").strip()
            if not symbol:
                continue
            if request.venue and market.casefold() != request.venue.casefold():
                continue
            if request.canonical_id and item.get("canonical_id") != request.canonical_id:
                continue
            key = (_normalized(symbol), market.casefold())
            if key in seen:
                continue
            seen.add(key)
            discovery_candidates.append(item)
            if _normalized(symbol) == exact_query:
                exact.append(item)
            elif _normalized(str(item.get("name") or "")) == exact_query:
                name_exact.append(item)
        return exact or name_exact, discovery_candidates

    @staticmethod
    def _candidate_identity_level(item: dict[str, Any]) -> str | None:
        """Read, but never infer, the level declared by authoritative master data."""
        declared = item.get("identity_level")
        if declared is not None:
            return str(declared)
        raw_identity = item.get("asset_research_identity")
        if isinstance(raw_identity, Mapping):
            level = raw_identity.get("identity_level")
            return str(level) if level is not None else None
        return None

    @staticmethod
    def _build_identity(asset_type: PublicAssetType, item: dict[str, Any]) -> InstrumentIdentity:
        """Load a versioned master identity; never derive contract facts from a code.

        ``MarketInstrumentService`` remains a discovery service.  A candidate
        is analysable only when its approved master-data adapter attaches the
        complete, versioned ``asset_research_identity`` payload.  This avoids
        turning a display symbol such as ``IF2609`` or ``BTC/USDT`` into
        invented expiry, multiplier, quote-asset or issuer facts.
        """
        raw_identity = item.get("asset_research_identity")
        if not isinstance(raw_identity, Mapping):
            raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED")
        if "metadata_version" not in raw_identity:
            raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED")
        try:
            identity = InstrumentIdentity.model_validate(raw_identity)
        except ValidationError:
            raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED") from None

        symbol = str(item.get("symbol") or "").strip()
        market = str(item.get("market") or "").strip()
        if identity.asset_type != asset_type:
            raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED")
        if not symbol or _normalized(identity.display_symbol) != _normalized(symbol):
            raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED")
        if market and (identity.venue is None or identity.venue.casefold() != market.casefold()):
            raise InstrumentResolutionError("INSTRUMENT_UNSUPPORTED")
        return identity
