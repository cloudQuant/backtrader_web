"""Template marker for the SimNow certification workspace.

The certification cases are executed by ``run.py``.  This no-op Backtrader
strategy allows the existing strategy-template scanner to expose the workspace
in the application without turning a template scan into a CTP connection.
"""

from __future__ import annotations

import backtrader as bt


class SimNowCertificationStrategy(bt.Strategy):
    """Expose the SimNow certification workspace as a strategy template."""

    params = (("case_id", "C01"),)

    def next(self) -> None:
        """Do not trade during template preview or ordinary backtests."""
