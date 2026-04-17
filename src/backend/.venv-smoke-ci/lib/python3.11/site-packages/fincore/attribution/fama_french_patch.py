"""Patch file for Fama-French model with HML factor.

This module extends the base FamaFrenchModel to support
the Fama-French five-factor model which includes:
- Market factor (MKT)
- Size (SMB)
- Value (HML)
- Profitability (RMW)
- Investment (CMA)

Reference
----------
Fama, E. F., French, C. W., & Davis, D. K. (1993).
'Stocks, Bonds, Bills, and Inflation: International Evidence on Stock
Returns and Predictability. NBER Working Paper No. 4308.

The five-factor model extends the three-factor model by adding:
- RMW: Robust Minus Factor
- CMA: Conservative Minus Factor
"""

from __future__ import annotations

__all__ = ["FamaFrenchModelPatch"]


class FamaFrenchModelPatch:
    """Fama-French multi-factor model estimator.

    Supports 3-factor (MKT, SMB, HML) and 5-factor models with
    additional factors (RMW, CMA, Investment).
    """

    def __init__(
        self,
        model_type: str = "5factor",
        risk_free_rate: float = 0.0,
    ):
        """Initialize Fama-French model.

        Parameters
        ----------
        model_type : str, default "5factor"
            Factor model specification.
            Options: '3factor', '5factor', '4factor_mom'
        risk_free_rate : float, default 0.0
            Risk-free rate for excess returns calculation.
        """
        self.model_type = model_type
        self.risk_free_rate = risk_free_rate
        self._betas: dict[str, float] | None = None
        self._set_factors()

    def _set_factors(self) -> None:
        """Set factor list based on model type."""
        if self.model_type == "3factor":
            self.factors = ["MKT", "SMB", "HML"]
        elif self.model_type == "5factor":
            self.factors = ["MKT", "SMB", "HML", "RMW", "CMA"]
        elif self.model_type == "4factor_mom":
            self.factors = ["MKT", "SMB", "HML", "MOM"]
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}. Use: '3factor', '5factor', '4factor_mom'")
