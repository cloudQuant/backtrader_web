"""Advanced performance attribution module.

Provides Brinson attribution, Fama-French multi-factor models,
style analysis, and timing attribution.
"""

from __future__ import annotations

from fincore.attribution.brinson import brinson_attribution, brinson_results
from fincore.attribution.fama_french import FamaFrenchModel
from fincore.attribution.style import (
    StyleResult,
    analyze_performance_by_style,
    calculate_regression_attribution,
    calculate_style_tilts,
    style_analysis,
)

__all__ = [
    "FamaFrenchModel",
    "StyleResult",
    "analyze_performance_by_style",
    "brinson_attribution",
    "brinson_results",
    "calculate_regression_attribution",
    "calculate_style_tilts",
    "style_analysis",
]
