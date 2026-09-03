"""Template marker for the Hongyuan penetration certification workspace.

The 33 certification cases are executed by ``run.py``.  This no-op strategy
keeps the workspace visible to the existing live-strategy template scanner.
"""

from __future__ import annotations

import backtrader as bt


class HongyuanPenetrationCertificationStrategy(bt.Strategy):
    """Expose the Hongyuan workspace without trading during template preview."""

    params = (("case_id", "C01"),)

    def next(self) -> None:
        """Do not trade during template preview or ordinary backtests."""
