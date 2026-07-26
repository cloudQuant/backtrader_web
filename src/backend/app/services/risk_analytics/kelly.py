"""Kelly position sizing service."""

from app.schemas.backtest import TradeRecord
from app.schemas.risk_analytics import KellyResult


class KellyService:
    """Calculate Kelly position sizing recommendations from closed trades."""

    def calculate(self, trades: list[TradeRecord], *, min_trades: int = 3) -> KellyResult:
        """Calculate full, half, and quarter Kelly fractions."""
        pnl_values = [
            float(trade.pnlcomm if trade.pnlcomm is not None else trade.pnl or 0.0)
            for trade in trades
        ]
        closed = [value for value in pnl_values if value != 0]
        if len(closed) < min_trades:
            return KellyResult(
                status="degraded",
                trade_count=len(closed),
                reason="insufficient_trades",
            )

        wins = [value for value in closed if value > 0]
        losses = [abs(value) for value in closed if value < 0]
        if not wins or not losses:
            return KellyResult(
                status="degraded",
                trade_count=len(closed),
                reason="missing_win_or_loss_samples",
            )

        win_rate = len(wins) / len(closed)
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
        full_kelly = max(0.0, min(1.0, (payoff_ratio * win_rate - (1 - win_rate)) / payoff_ratio))
        return KellyResult(
            status="ok",
            trade_count=len(closed),
            win_rate=round(win_rate, 6),
            avg_win=round(avg_win, 6),
            avg_loss=round(avg_loss, 6),
            payoff_ratio=round(payoff_ratio, 6),
            full_kelly=round(full_kelly, 6),
            half_kelly=round(full_kelly / 2, 6),
            quarter_kelly=round(full_kelly / 4, 6),
            recommendation="fractional_kelly",
        )
