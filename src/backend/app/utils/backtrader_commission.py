"""Portable Backtrader commission models for contract-backed strategies.

The local Backtrader fork supplies these commission models.  Production and
CI may instead use the public ``backtrader`` package, whose commission module
does not provide the role-aware futures variants.  Keep the runtime behaviour
consistent in either environment without requiring a sibling source checkout.
"""

from __future__ import annotations

from typing import Any

try:
    import backtrader.comminfo as _native_comminfo

    _NativeComminfoFuturesFixed = _native_comminfo.ComminfoFuturesFixed
    _NativeComminfoFuturesInverse = _native_comminfo.ComminfoFuturesInverse
    _NativeComminfoFuturesMixed = _native_comminfo.ComminfoFuturesMixed
    _NativeComminfoFuturesPercent = _native_comminfo.ComminfoFuturesPercent
except (AttributeError, ImportError):
    import backtrader as bt

    class _RoleAwareFuturesCommission(bt.CommInfoBase):
        """Add contract roles and fixed-margin support to upstream Backtrader."""

        params: Any = (
            ("margin_amount", None),
            ("maker_commission", None),
            ("taker_commission", None),
            ("open_commission", None),
            ("close_commission", None),
            ("close_today_commission", None),
            ("close_yesterday_commission", None),
            ("stocklike", False),
            ("commtype", bt.CommInfoBase.COMM_PERC),
            ("percabs", True),
        )

        def get_param(self, name: str) -> Any:
            """Mirror the local fork's parameter accessor."""
            return getattr(self.p, name)

        def _commission_rate(self, role: str | None = None) -> float:
            role_text = str(role or "").strip().lower()
            if role_text in {"open", "opened"} and self.p.open_commission is not None:
                return float(self.p.open_commission)
            if role_text in {"close_today", "closetoday"}:
                if self.p.close_today_commission is not None:
                    return float(self.p.close_today_commission)
                if self.p.close_commission is not None:
                    return float(self.p.close_commission)
            if role_text in {"close_yesterday", "closeyesterday"}:
                if self.p.close_yesterday_commission is not None:
                    return float(self.p.close_yesterday_commission)
                if self.p.close_commission is not None:
                    return float(self.p.close_commission)
            if role_text in {"close", "closed"} and self.p.close_commission is not None:
                return float(self.p.close_commission)
            if role_text == "maker" and self.p.maker_commission is not None:
                return float(self.p.maker_commission)
            if role_text == "taker" and self.p.taker_commission is not None:
                return float(self.p.taker_commission)
            return float(self.p.commission)

        def getcommission(self, size: float, price: float, role: str | None = None) -> float:
            """Calculate a role-aware commission without changing broker calls."""
            return self._getcommission(size, price, pseudoexec=True, role=role)

        def confirmexec(self, size: float, price: float, role: str | None = None) -> float:
            """Confirm a role-aware commission after execution."""
            return self._getcommission(size, price, pseudoexec=False, role=role)

        def get_margin(self, price: float) -> float:
            """Use a fixed exchange margin when supplied, otherwise rate margin."""
            if self.p.margin_amount is not None and self.p.margin_amount > 0:
                return float(self.p.margin_amount)
            margin = 1.0 if self.p.margin is None else float(self.p.margin)
            return float(price) * float(self.p.mult) * margin

    class ComminfoFuturesPercent(_RoleAwareFuturesCommission):
        """Futures commission calculated from traded notional."""

        def _getcommission(
            self, size: float, price: float, pseudoexec: bool, role: str | None = None
        ) -> float:
            _ = pseudoexec
            return abs(size) * price * float(self.p.mult) * self._commission_rate(role)

    class ComminfoFuturesMixed(ComminfoFuturesPercent):
        """Futures commission combining notional and per-lot charges."""

        params: Any = (
            ("commission_amount", 0.0),
            ("open_commission_amount", None),
            ("close_commission_amount", None),
            ("close_today_commission_amount", None),
            ("close_yesterday_commission_amount", None),
        )

        def _commission_amount(self, role: str | None = None) -> float:
            role_text = str(role or "").strip().lower()
            if role_text in {"open", "opened"} and self.p.open_commission_amount is not None:
                return float(self.p.open_commission_amount)
            if role_text in {"close_today", "closetoday"}:
                if self.p.close_today_commission_amount is not None:
                    return float(self.p.close_today_commission_amount)
                if self.p.close_commission_amount is not None:
                    return float(self.p.close_commission_amount)
            if role_text in {"close_yesterday", "closeyesterday"}:
                if self.p.close_yesterday_commission_amount is not None:
                    return float(self.p.close_yesterday_commission_amount)
                if self.p.close_commission_amount is not None:
                    return float(self.p.close_commission_amount)
            if role_text in {"close", "closed"} and self.p.close_commission_amount is not None:
                return float(self.p.close_commission_amount)
            return float(self.p.commission_amount)

        def _getcommission(
            self, size: float, price: float, pseudoexec: bool, role: str | None = None
        ) -> float:
            percent = super()._getcommission(size, price, pseudoexec, role)
            return percent + abs(size) * self._commission_amount(role)

    class ComminfoFuturesInverse(ComminfoFuturesMixed):
        """Inverse futures commission and PnL using fixed contract notional."""

        def _getcommission(
            self, size: float, price: float, pseudoexec: bool, role: str | None = None
        ) -> float:
            _ = price, pseudoexec
            return abs(size) * (
                float(self.p.mult) * self._commission_rate(role) + self._commission_amount(role)
            )

        def get_margin(self, price: float) -> float:
            """Return margin from fixed contract value for inverse products."""
            _ = price
            if self.p.margin_amount is not None and self.p.margin_amount > 0:
                return float(self.p.margin_amount)
            margin = 1.0 if self.p.margin is None else float(self.p.margin)
            return float(self.p.mult) * margin

        def profitandloss(self, size: float, price: float, newprice: float) -> float:
            """Return inverse-contract quote-equivalent profit and loss."""
            if not price or not newprice:
                return 0.0
            return size * float(self.p.mult) * ((newprice / price) - 1.0)

        def cashadjust(self, size: float, price: float, newprice: float) -> float:
            """Mark inverse positions using the same PnL rule."""
            return self.profitandloss(size, price, newprice)

    class ComminfoFuturesFixed(_RoleAwareFuturesCommission):
        """Futures commission calculated as a fixed per-lot charge."""

        params: Any = (("commtype", bt.CommInfoBase.COMM_FIXED),)

        def _getcommission(
            self, size: float, price: float, pseudoexec: bool, role: str | None = None
        ) -> float:
            _ = price, pseudoexec
            return abs(size) * self._commission_rate(role)

else:
    # The fallback branch defines these as classes; re-export the native
    # classes when available. Mypy cannot reconcile that runtime-only choice.
    ComminfoFuturesFixed = _NativeComminfoFuturesFixed  # type: ignore[misc]
    ComminfoFuturesInverse = _NativeComminfoFuturesInverse  # type: ignore[misc]
    ComminfoFuturesMixed = _NativeComminfoFuturesMixed  # type: ignore[misc]
    ComminfoFuturesPercent = _NativeComminfoFuturesPercent  # type: ignore[misc]


__all__ = [
    "ComminfoFuturesFixed",
    "ComminfoFuturesInverse",
    "ComminfoFuturesMixed",
    "ComminfoFuturesPercent",
]
