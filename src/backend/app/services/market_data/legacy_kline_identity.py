"""Exact frozen-identity matching for the legacy K-line display token."""

from __future__ import annotations

from app.schemas.asset_research import InstrumentIdentity, StockIdentityDetails


def matches_legacy_kline_display_token(
    identity: InstrumentIdentity,
    *,
    token: str,
) -> bool:
    """Accept only one exact server-frozen stock token representation.

    Historical callers may use the provider's bare six-digit display symbol or
    the stock identity's separately frozen exchange symbol such as
    ``000001.SZ``.  This is an exact alias projection stored in the identity;
    it never splits suffixes, infers a market, normalizes case, or looks up a
    nearby symbol.
    """
    if identity.asset_type != "stock":
        return False
    if identity.display_symbol == token:
        return True
    details = identity.details
    return isinstance(details, StockIdentityDetails) and details.exchange_symbol == token


__all__ = ["matches_legacy_kline_display_token"]
