"""
Backtest result analyzer for parsing backtrader backtest results.

This module provides classes and functions to analyze and parse
backtrader backtest results, including metrics calculation and
equity curve generation.
"""
import backtrader as bt
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
import json


@dataclass
class TradeRecord:
    """Represents a single trade record.

    Attributes:
        datetime: Trade date and time.
        direction: Trade direction (buy/sell).
        price: Execution price.
        size: Position size.
        value: Trade value.
        pnl: Profit and loss.
        pnl_percent: Profit and loss percentage.
    """
    datetime: str
    direction: str  # buy/sell
    price: float
    size: int
    value: float
    pnl: float = 0.0
    pnl_percent: float = 0.0


@dataclass
class BacktestResult:
    """Represents complete backtest results.

    Attributes:
        strategy_name: Name of the strategy.
        symbol: Trading symbol.
        start_date: Backtest start date.
        end_date: Backtest end date.
        initial_cash: Initial capital amount.
        final_value: Final portfolio value.
        total_return: Total return percentage.
        annual_return: Annualized return percentage.
        sharpe_ratio: Sharpe ratio.
        max_drawdown: Maximum drawdown percentage.
        total_trades: Total number of trades.
        profitable_trades: Number of profitable trades.
        losing_trades: Number of losing trades.
        win_rate: Win rate percentage.
        equity_curve: List of equity values.
        equity_dates: List of dates for equity curve.
        drawdown_curve: List of drawdown values.
        trades: List of trade records.
    """
    # Basic information
    strategy_name: str = ""
    symbol: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 100000.0
    final_value: float = 100000.0

    # Return metrics
    total_return: float = 0.0
    annual_return: float = 0.0

    # Risk metrics
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    # Trading statistics
    total_trades: int = 0
    profitable_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # Curve data
    equity_curve: List[float] = field(default_factory=list)
    equity_dates: List[str] = field(default_factory=list)
    drawdown_curve: List[float] = field(default_factory=list)

    # Trade records
    trades: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class EquityObserver(bt.Observer):
    """Observer for tracking equity curve value.

    This observer records the portfolio value at each time step
    during the backtest.
    """
    lines = ('value',)
    plotinfo = dict(plot=True, subplot=True)

    def next(self):
        """Update equity value on each step."""
        self.lines.value[0] = self._owner.broker.getvalue()


class BacktestAnalyzer:
    """Analyzer for running and parsing backtrader backtests.

    This class sets up analyzers, runs the backtest, and parses
    the results into a structured BacktestResult object.
    """

    def __init__(self, cerebro: bt.Cerebro):
        """
        Initialize the BacktestAnalyzer.

        Args:
            cerebro: Configured Cerebro instance.
        """
        self.cerebro = cerebro
        self.results = None
        self._setup_analyzers()

    def _setup_analyzers(self):
        """Add built-in analyzers to the cerebro instance."""
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02)
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        self.cerebro.addanalyzer(bt.analyzers.TimeReturn, _name='time_return', timeframe=bt.TimeFrame.Days)

        # Add equity curve observer
        self.cerebro.addobserver(EquityObserver)

    def run(self) -> BacktestResult:
        """
        Run backtest and return parsed results.

        Returns:
            BacktestResult object with all metrics and curves.
        """
        initial_cash = self.cerebro.broker.getvalue()
        self.results = self.cerebro.run()

        return self._parse_results(initial_cash)

    def _parse_results(self, initial_cash: float) -> BacktestResult:
        """
        Parse backtest results into structured format.

        Args:
            initial_cash: Initial capital amount.

        Returns:
            BacktestResult with parsed metrics and data.
        """
        strat = self.results[0]
        final_value = self.cerebro.broker.getvalue()

        # Basic return calculation
        total_return = ((final_value - initial_cash) / initial_cash) * 100

        # Get data time range
        data = strat.data
        start_date = bt.num2date(data.datetime.array[0]).strftime("%Y-%m-%d")
        end_date = bt.num2date(data.datetime.array[-1]).strftime("%Y-%m-%d")

        # Calculate annualized return
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = (end_dt - start_dt).days
        years = total_days / 365.0 if total_days > 0 else 1
        annual_return = (((final_value / initial_cash) ** (1 / years)) - 1) * 100 if years > 0 else 0

        # Sharpe ratio
        sharpe_ratio = 0.0
        try:
            sharpe_analysis = strat.analyzers.sharpe.get_analysis()
            sharpe_ratio = sharpe_analysis.get('sharperatio') or 0.0
        except Exception:
            pass

        # Maximum drawdown
        max_drawdown = 0.0
        try:
            drawdown_analysis = strat.analyzers.drawdown.get_analysis()
            max_drawdown = drawdown_analysis.get('max', {}).get('drawdown', 0.0) or 0.0
        except Exception:
            pass

        # Trading statistics
        total_trades = 0
        profitable_trades = 0
        losing_trades = 0
        try:
            trade_analysis = strat.analyzers.trades.get_analysis()
            total_trades = trade_analysis.get('total', {}).get('total', 0) or 0
            profitable_trades = trade_analysis.get('won', {}).get('total', 0) or 0
            losing_trades = trade_analysis.get('lost', {}).get('total', 0) or 0
        except Exception:
            pass

        win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0

        # Get equity curve
        equity_curve, equity_dates, drawdown_curve = self._get_equity_curve(strat, initial_cash)

        # Strategy name
        strategy_name = strat.__class__.__name__

        # Symbol code
        symbol = getattr(data, '_name', '') or getattr(data._dataname, 'name', 'Unknown') if hasattr(data, '_dataname') else 'Unknown'

        return BacktestResult(
            strategy_name=strategy_name,
            symbol=str(symbol),
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            final_value=round(final_value, 2),
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            sharpe_ratio=round(sharpe_ratio, 2) if sharpe_ratio else 0.0,
            max_drawdown=round(max_drawdown, 2),
            total_trades=total_trades,
            profitable_trades=profitable_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 1),
            equity_curve=equity_curve,
            equity_dates=equity_dates,
            drawdown_curve=drawdown_curve,
            trades=[],
        )

    def _get_equity_curve(self, strat, initial_cash: float):
        """
        Extract equity curve data from strategy results.

        Args:
            strat: Strategy instance with analyzers.
            initial_cash: Initial capital for baseline.

        Returns:
            Tuple of (equity_curve, equity_dates, drawdown_curve).
        """
        equity_curve = []
        equity_dates = []
        drawdown_curve = []

        try:
            # Get daily returns from TimeReturn analyzer
            time_return = strat.analyzers.time_return.get_analysis()

            current_value = initial_cash
            peak = initial_cash

            for dt, ret in sorted(time_return.items()):
                current_value = current_value * (1 + (ret or 0))
                equity_curve.append(round(current_value, 2))

                if hasattr(dt, 'strftime'):
                    equity_dates.append(dt.strftime("%Y-%m-%d"))
                else:
                    equity_dates.append(str(dt))

                if current_value > peak:
                    peak = current_value
                dd = ((peak - current_value) / peak) * 100 if peak > 0 else 0
                drawdown_curve.append(round(dd, 2))

        except Exception as e:
            # Simplified fallback handling
            data = strat.data
            equity_curve = [initial_cash, self.cerebro.broker.getvalue()]
            equity_dates = [
                bt.num2date(data.datetime.array[0]).strftime("%Y-%m-%d"),
                bt.num2date(data.datetime.array[-1]).strftime("%Y-%m-%d")
            ]
            drawdown_curve = [0, 0]

        return equity_curve, equity_dates, drawdown_curve
