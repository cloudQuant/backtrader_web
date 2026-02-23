"""
Backtest analytics service.
"""
from typing import Dict, List, Optional

import numpy as np

from app.schemas.analytics import (
    DrawdownPoint,
    EquityPoint,
    MonthlyReturn,
    MonthlyReturnsResponse,
    PerformanceMetrics,
    TradeRecord,
    TradeSignal,
)


class AnalyticsService:
    """Service for analyzing backtest results and calculating performance metrics."""

    def calculate_metrics(self, result_data: Dict) -> PerformanceMetrics:
        """Calculate performance metrics from backtest results.

        Args:
            result_data: Dictionary containing backtest result data including
                equity_curve and trades.

        Returns:
            PerformanceMetrics: Calculated metrics including returns, drawdown,
                Sharpe ratio, win rate, and trade statistics.
        """
        equity_curve = result_data.get('equity_curve', [])
        trades = result_data.get('trades', [])

        if not equity_curve:
            return PerformanceMetrics(
                initial_capital=0,
                final_assets=0,
                total_return=0,
                annualized_return=0,
                max_drawdown=0,
            )

        initial = equity_curve[0].get('total_assets', 0)
        final = equity_curve[-1].get('total_assets', 0)

        # Total return
        total_return = (final - initial) / initial if initial else 0

        # Annualized return
        days = len(equity_curve)
        annualized = (1 + total_return) ** (252 / days) - 1 if days > 0 else 0

        # Maximum drawdown
        max_dd, max_dd_duration = self._calculate_max_drawdown(equity_curve)

        # Sharpe ratio
        returns = self._calculate_daily_returns(equity_curve)
        sharpe = self._calculate_sharpe(returns)

        # Trade statistics
        wins = [t for t in trades if (t.get('pnl') or 0) > 0]
        losses = [t for t in trades if (t.get('pnl') or 0) < 0]

        win_rate = len(wins) / len(trades) if trades else 0
        avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
        avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 0
        profit_factor = avg_win / avg_loss if avg_loss else 0

        # Average holding days
        holding_days = [t.get('barlen', 0) for t in trades if t.get('barlen')]
        avg_holding = np.mean(holding_days) if holding_days else 0

        # Consecutive wins/losses
        max_wins = self._max_consecutive(trades, True)
        max_losses = self._max_consecutive(trades, False)

        # Calmar ratio
        calmar = annualized / abs(max_dd) if max_dd != 0 else None

        return PerformanceMetrics(
            initial_capital=round(initial, 2),
            final_assets=round(final, 2),
            total_return=round(total_return, 6),
            annualized_return=round(annualized, 6),
            max_drawdown=round(max_dd, 6),
            max_drawdown_duration=max_dd_duration,
            sharpe_ratio=round(sharpe, 4) if sharpe else None,
            calmar_ratio=round(calmar, 4) if calmar else None,
            win_rate=round(win_rate, 4),
            profit_factor=round(profit_factor, 4),
            trade_count=len(trades),
            avg_trade_return=round(total_return / len(trades), 6) if trades else 0,
            avg_holding_days=round(avg_holding, 1),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            max_consecutive_wins=max_wins,
            max_consecutive_losses=max_losses,
        )

    def _calculate_max_drawdown(self, equity_curve: List[Dict]) -> tuple:
        """Calculate maximum drawdown and duration from equity curve.

        Args:
            equity_curve: List of equity data points.

        Returns:
            A tuple of (max_drawdown, max_drawdown_duration).
        """
        if not equity_curve:
            return 0, 0

        values = [e['total_assets'] for e in equity_curve]
        peak = values[0]
        max_dd = 0
        max_dd_duration = 0
        current_duration = 0

        for value in values:
            if value > peak:
                peak = value
                current_duration = 0
            else:
                dd = (value - peak) / peak if peak > 0 else 0
                current_duration += 1
                if dd < max_dd:
                    max_dd = dd
                    max_dd_duration = current_duration

        return max_dd, max_dd_duration

    def _calculate_daily_returns(self, equity_curve: List[Dict]) -> List[float]:
        """Calculate daily returns from equity curve.

        Args:
            equity_curve: List of equity data points.

        Returns:
            List of daily return percentages.
        """
        if len(equity_curve) < 2:
            return []

        values = [e['total_assets'] for e in equity_curve]
        returns = []
        for i in range(1, len(values)):
            if values[i-1] > 0:
                ret = (values[i] - values[i-1]) / values[i-1]
                returns.append(ret)
        return returns

    def _calculate_sharpe(
        self,
        returns: List[float],
        rf: float = 0
    ) -> Optional[float]:
        """Calculate Sharpe ratio from returns.

        Args:
            returns: List of daily returns.
            rf: Risk-free rate (annualized). Defaults to 0.

        Returns:
            Sharpe ratio (annualized), or None if insufficient data.
        """
        if len(returns) < 2:
            return None

        returns_arr = np.array(returns)
        excess_returns = returns_arr - rf / 252

        if np.std(excess_returns) == 0:
            return None

        return float(
            np.sqrt(252) * np.mean(excess_returns) / np.std(excess_returns)
        )

    def _max_consecutive(self, trades: List[Dict], win: bool) -> int:
        """Calculate maximum consecutive wins or losses.

        Args:
            trades: List of trade records.
            win: True to count wins, False to count losses.

        Returns:
            Maximum consecutive count of wins or losses.
        """
        max_count = 0
        current = 0

        for t in trades:
            pnl = t.get('pnl') or 0
            is_win = pnl > 0
            if is_win == win:
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0

        return max_count

    def process_trades(self, raw_trades: List[Dict]) -> List[TradeRecord]:
        """Process and format trade records.

        Args:
            raw_trades: List of raw trade dictionaries from backtest.

        Returns:
            List of formatted TradeRecord objects with calculated fields.
        """
        processed = []
        cumulative_pnl = 0

        for i, t in enumerate(raw_trades):
            pnl = t.get('pnl') or t.get('pnlcomm', 0)
            cumulative_pnl += pnl

            # Calculate return percentage
            value = t.get('value', 0)
            return_pct = pnl / value if value else 0

            processed.append(TradeRecord(
                id=i + 1,
                datetime=t.get('datetime', ''),
                symbol=t.get('symbol', 'unknown'),
                direction=t.get('direction', 'unknown'),
                price=round(t.get('price', 0), 4),
                size=abs(t.get('size', 0)),
                value=round(abs(value), 2),
                commission=round(t.get('commission', 0), 4),
                pnl=round(pnl, 2) if pnl else None,
                return_pct=round(return_pct, 6) if return_pct else None,
                holding_days=t.get('barlen'),
                cumulative_pnl=round(cumulative_pnl, 2),
            ))

        return processed

    def process_equity_curve(self, raw_curve: List[Dict]) -> List[EquityPoint]:
        """Process and format equity curve data.

        Args:
            raw_curve: List of raw equity data points.

        Returns:
            List of formatted EquityPoint objects.
        """
        return [
            EquityPoint(
                date=e.get('date', ''),
                total_assets=e.get('total_assets', 0),
                cash=e.get('cash', 0),
                position_value=e.get('position_value', 0),
            )
            for e in raw_curve
        ]

    def process_drawdown_curve(self, raw_curve: List[Dict]) -> List[DrawdownPoint]:
        """Process and format drawdown curve data.

        Args:
            raw_curve: List of raw drawdown data points.

        Returns:
            List of formatted DrawdownPoint objects.
        """
        return [
            DrawdownPoint(
                date=d.get('date', ''),
                drawdown=d.get('drawdown', 0),
                peak=d.get('peak', 0),
                trough=d.get('trough', 0),
            )
            for d in raw_curve
        ]

    def process_signals(self, raw_signals: List[Dict]) -> List[TradeSignal]:
        """Process and format trade signals.

        Args:
            raw_signals: List of raw signal dictionaries.

        Returns:
            List of formatted TradeSignal objects.
        """
        return [
            TradeSignal(
                date=s.get('date', ''),
                type=s.get('type', ''),
                price=s.get('price', 0),
                size=s.get('size', 0),
            )
            for s in raw_signals
        ]

    def process_monthly_returns(
        self,
        raw_returns: Dict
    ) -> MonthlyReturnsResponse:
        """Process and format monthly returns data.

        Args:
            raw_returns: Dictionary with (year, month) tuples as keys and
                return percentages as values.

        Returns:
            MonthlyReturnsResponse with returns, years, and summary by year.
        """
        returns = []
        years = set()

        for (year, month), ret in raw_returns.items():
            returns.append(MonthlyReturn(year=year, month=month, return_pct=ret))
            years.add(year)

        # Yearly summary
        summary = {}
        for year in years:
            year_returns = [r.return_pct for r in returns if r.year == year]
            # Compound annual return calculation
            total = 1
            for r in year_returns:
                total *= (1 + r)
            summary[year] = round(total - 1, 6)

        return MonthlyReturnsResponse(
            returns=sorted(returns, key=lambda x: (x.year, x.month)),
            years=sorted(list(years)),
            summary=summary,
        )

    def calculate_indicators(self, klines: List[Dict]) -> Dict[str, List[Optional[float]]]:
        """Calculate technical indicators from K-line data.

        Args:
            klines: List of K-line dictionaries with close prices.

        Returns:
            Dictionary mapping indicator names to lists of values.
        """
        if not klines:
            return {}

        closes = [k.get('close', 0) for k in klines]

        def ma(period: int) -> List[Optional[float]]:
            result = [None] * (period - 1)
            for i in range(period - 1, len(closes)):
                avg = sum(closes[i - period + 1:i + 1]) / period
                result.append(round(avg, 4))
            return result

        return {
            'ma5': ma(5),
            'ma10': ma(10),
            'ma20': ma(20),
            'ma60': ma(60) if len(closes) >= 60 else [],
        }
