"""Deterministic futures research primitives."""

from app.services.asset_research.plugins.futures.term_structure import (
    FuturesTermStructureInput,
    calculate_futures_term_structure,
)

__all__ = ["FuturesTermStructureInput", "calculate_futures_term_structure"]
