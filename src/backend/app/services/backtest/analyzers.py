"""
Backtrader analyzer extensions.

Collects detailed backtest data for analytics and reporting.
"""

import datetime
import logging
import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

try:
    import backtrader as bt
except Exception as exc:  # pragma: no cover - depends on optional native runtime
    bt = None
    logger.warning("backtrader is unavailable; analyzer base classes use fallback mode: %s", exc)

if TYPE_CHECKING:
    # backtrader has no type stubs (ignore_missing_imports). Aliasing to ``Any``
    # lets mypy accept ``AnalyzerBase`` as a base class (inheriting from Any is allowed).
    AnalyzerBase: Any = object
else:
    AnalyzerBase = getattr(bt, "Analyzer", object) if bt is not None else object
    if AnalyzerBase is object:
        logger.warning(
            "backtrader.Analyzer is unavailable; custom analyzers are running in fallback mode"
        )


class DetailedTradeAnalyzer(AnalyzerBase):
    """Detailed trade analyzer that records detailed information for each trade.

    Attributes:
        trades: List of trade records with detailed information.
        trade_count: Total number of trades recorded.
    """

    def __init__(self) -> None:
        """Initialize the trade analyzer."""
        self.trades: list[dict[str, Any]] = []
        self.trade_count = 0

    def notify_trade(self, trade: Any) -> None:
        """Called when a trade is closed to record its details.

        Args:
            trade: The closed trade object from backtrader.
        """
        if trade.isclosed:
            self.trade_count += 1
            self.trades.append(
                {
                    "id": self.trade_count,
                    "ref": trade.ref,
                    "datetime": self.datas[0].datetime.datetime(0).strftime("%Y-%m-%d %H:%M:%S"),
                    "symbol": trade.data._name or "unknown",
                    "direction": "buy" if trade.history[0].event.size > 0 else "sell",
                    "size": abs(trade.size),
                    "price": trade.price,
                    "value": abs(trade.value),
                    "commission": trade.commission,
                    "pnl": trade.pnl,
                    "pnlcomm": trade.pnlcomm,
                    "barlen": trade.barlen,
                }
            )

    def get_analysis(self) -> dict[str, Any]:
        """Return the analysis results.

        Returns:
            A dictionary containing the list of detailed trades.
        """
        return {"trades": self.trades}


class EquityCurveAnalyzer(AnalyzerBase):
    """Equity curve analyzer that records daily changes in account value.

    Attributes:
        equity_curve: List of daily equity records.
        _last_value: The last recorded portfolio value.
    """

    def __init__(self) -> None:
        """Initialize the equity curve analyzer."""
        self.equity_curve: list[dict[str, Any]] = []
        self._last_value: float | None = None

    def start(self) -> None:
        """Record the initial portfolio value when backtest starts."""
        self._last_value = self.strategy.broker.getvalue()

    def next(self) -> None:
        """Record equity data for each bar."""
        dt = self.datas[0].datetime.datetime(0)
        total = self.strategy.broker.getvalue()
        cash = self.strategy.broker.getcash()
        position_value = total - cash

        self.equity_curve.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "total_assets": round(total, 2),
                "cash": round(cash, 2),
                "position_value": round(position_value, 2),
            }
        )

    def get_analysis(self) -> dict[str, Any]:
        """Return the analysis results.

        Returns:
            A dictionary containing the equity curve data.
        """
        return {"equity_curve": self.equity_curve}


class TradeSignalAnalyzer(AnalyzerBase):
    """Trade signal analyzer that records buy and sell signals.

    Attributes:
        signals: List of trade signals with execution details.
    """

    def __init__(self) -> None:
        """Initialize the trade signal analyzer."""
        self.signals: list[dict[str, Any]] = []

    def notify_order(self, order: Any) -> None:
        """Called when an order is completed to record the signal.

        Args:
            order: The completed order object from backtrader.
        """
        if order.status == order.Completed:
            signal_type = "buy" if order.isbuy() else "sell"
            dt = self.datas[0].datetime.datetime(0)
            self.signals.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "type": signal_type,
                    "price": round(order.executed.price, 4),
                    "size": abs(order.executed.size),
                }
            )

    def get_analysis(self) -> dict[str, Any]:
        """Return the analysis results.

        Returns:
            A dictionary containing the list of trade signals.
        """
        return {"signals": self.signals}


class MonthlyReturnsAnalyzer(AnalyzerBase):
    """Monthly returns analyzer that calculates returns for each month.

    Attributes:
        monthly_returns: Dictionary mapping (year, month) tuples to return values.
        month_start_value: Portfolio value at the start of the current month.
        current_month: The current (year, month) tuple being tracked.
    """

    def __init__(self) -> None:
        """Initialize the monthly returns analyzer."""
        self.monthly_returns: dict[tuple[int, int], float] = {}
        self.month_start_value: float | None = None
        self.current_month: tuple[int, int] | None = None

    def start(self) -> None:
        """Record the initial portfolio value when backtest starts."""
        self.month_start_value = self.strategy.broker.getvalue()

    def next(self) -> None:
        """Calculate monthly returns when month changes."""
        dt = self.datas[0].datetime.datetime(0)
        month_key = (dt.year, dt.month)
        current_value = self.strategy.broker.getvalue()

        if self.current_month != month_key:
            # Record last month's return
            if self.current_month and self.month_start_value:
                ret = (current_value - self.month_start_value) / self.month_start_value
                self.monthly_returns[self.current_month] = round(ret, 6)

            # Start new month
            self.month_start_value = current_value
            self.current_month = month_key

    def stop(self) -> None:
        """Record the final month's return when backtest ends."""
        if self.current_month and self.month_start_value:
            current_value = self.strategy.broker.getvalue()
            ret = (current_value - self.month_start_value) / self.month_start_value
            self.monthly_returns[self.current_month] = round(ret, 6)

    def get_analysis(self) -> dict[str, Any]:
        """Return the analysis results.

        Returns:
            A dictionary containing monthly return data.
        """
        return {"monthly_returns": self.monthly_returns}


class DrawdownAnalyzer(AnalyzerBase):
    """Drawdown analyzer that records daily drawdown metrics.

    Attributes:
        drawdown_curve: List of daily drawdown records.
        peak: The highest portfolio value observed.
    """

    def __init__(self) -> None:
        """Initialize the drawdown analyzer."""
        self.drawdown_curve: list[dict[str, Any]] = []
        self.peak = 0

    def start(self) -> None:
        """Initialize the peak value when backtest starts."""
        self.peak = self.strategy.broker.getvalue()

    def next(self) -> None:
        """Calculate drawdown for each bar."""
        dt = self.datas[0].datetime.datetime(0)
        current = self.strategy.broker.getvalue()

        if current > self.peak:
            self.peak = current

        dd = (current - self.peak) / self.peak if self.peak > 0 else 0

        self.drawdown_curve.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "drawdown": round(dd, 6),
                "peak": round(self.peak, 2),
                "trough": round(current, 2),
            }
        )

    def get_analysis(self) -> dict[str, Any]:
        """Return the analysis results.

        Returns:
            A dictionary containing the drawdown curve data.
        """
        return {"drawdown_curve": self.drawdown_curve}


def get_all_analyzers() -> dict[str, Any]:
    """Get all custom analyzers.

    Returns:
        A dictionary mapping analyzer names to their classes.
    """
    return {
        "detailed_trades": DetailedTradeAnalyzer,
        "equity_curve": EquityCurveAnalyzer,
        "trade_signals": TradeSignalAnalyzer,
        "monthly_returns": MonthlyReturnsAnalyzer,
        "drawdown": DrawdownAnalyzer,
    }


class FincoreAdapter:
    """Adapter for fincore domain metrics with a compatible manual fallback.

    Fincore 0.5 uses focused domain modules instead of root-level metric
    functions. The adapter accepts the platform's equity-curve representation,
    converts it to simple returns at the boundary, and delegates to those
    domain modules. When the optional dependency is unavailable or rejects an
    input, a semantically equivalent manual calculation is used instead.

    Attributes:
        use_fincore: If True, prefer fincore domain metrics. If False, always
            use the manual fallback.

    Example:
        >>> adapter = FincoreAdapter()
        >>> sharpe = adapter.calculate_sharpe_ratio(returns, 0.0001)
        >>> adapter_with_fincore = FincoreAdapter(use_fincore=True)
        >>> sharpe_fc = adapter_with_fincore.calculate_sharpe_ratio(returns, 0.0001)
    """

    MANUAL_SOURCE = "manual"
    FINCORE_SOURCE = "fincore"

    def __init__(self, use_fincore: bool = False):
        """Initialize the FincoreAdapter.

        Args:
            use_fincore: Whether to prefer fincore domain metrics. Defaults to
                False for backward compatibility.
        """
        self.use_fincore = use_fincore
        self._last_calculation_source = self.MANUAL_SOURCE

    @property
    def last_calculation_source(self) -> str:
        """Return the source used by the most recently calculated metric."""
        return self._last_calculation_source

    @staticmethod
    def _as_finite_array(values: Any) -> Any | None:
        """Return a one-dimensional finite float array or ``None``."""
        import numpy as np

        try:
            array = np.asarray(values, dtype=float)
        except (TypeError, ValueError):
            return None
        if array.ndim != 1 or len(array) == 0 or not np.all(np.isfinite(array)):
            return None
        return array

    @staticmethod
    def _periods_per_year(value: float) -> float:
        """Normalize an annualization factor to a finite positive value."""
        try:
            periods = float(value)
        except (TypeError, ValueError):
            return 252.0
        return periods if math.isfinite(periods) and periods > 0 else 252.0

    def _fincore_equity_returns(self, equity_curve: list[Any]) -> Any | None:
        """Convert a valid equity curve with fincore's public returns utility."""
        if not self.use_fincore:
            return None

        values = self._as_finite_array(equity_curve)
        if values is None or len(values) < 2 or (values <= 0).any():
            return None

        try:
            from fincore.metrics.returns import simple_returns

            returns = simple_returns(values)
        except (ImportError, TypeError, ValueError):
            logger.debug("Unable to derive fincore returns; using manual metrics", exc_info=True)
            return None

        return returns if self._as_finite_array(returns) is not None else None

    def _try_fincore(self, operation: Callable[[], Any]) -> float | None:
        """Run one fincore operation and return a finite scalar result."""
        self._last_calculation_source = self.MANUAL_SOURCE
        if not self.use_fincore:
            return None

        try:
            result = float(operation())
        except (ArithmeticError, ImportError, TypeError, ValueError):
            logger.debug("Fincore metric failed; using manual fallback", exc_info=True)
            return None

        if not math.isfinite(result):
            return None

        self._last_calculation_source = self.FINCORE_SOURCE
        return result

    def calculate_sharpe_ratio(
        self,
        returns: list[Any],
        risk_free_rate: float = 0.0,
        periods_per_year: float = 252.0,
    ) -> float:
        """Calculate Sharpe ratio for a series of returns.

        The Sharpe ratio measures the performance of an investment compared
        to a risk-free asset, after adjusting for risk.

        Args:
            returns: Non-cumulative simple returns (for example, ``0.01`` for
                a 1% period return).
            risk_free_rate: Per-period risk-free return. Defaults to ``0.0``.
            periods_per_year: Annualization factor for the input frequency.

        Returns:
            Annualized Sharpe ratio. Returns ``0.0`` for insufficient or
            invalid data.

        Formula:
            Sharpe = mean(excess returns) / sample_std(excess returns)
                     * sqrt(periods_per_year)
        """
        self._last_calculation_source = self.MANUAL_SOURCE
        returns_array = self._as_finite_array(returns)
        if returns_array is None or len(returns_array) < 2:
            return 0.0

        import numpy as np

        annualization = self._periods_per_year(periods_per_year)

        def calculate_with_fincore() -> Any:
            from fincore.metrics.ratios import sharpe_ratio

            return sharpe_ratio(
                returns_array,
                risk_free=risk_free_rate,
                annualization=annualization,
            )

        fincore_result = self._try_fincore(calculate_with_fincore)
        if fincore_result is not None:
            return fincore_result

        excess_returns = returns_array - risk_free_rate
        std_dev = np.std(excess_returns, ddof=1)

        if not math.isfinite(float(std_dev)) or std_dev <= 0:
            return 0.0

        result = float(np.mean(excess_returns) / std_dev * math.sqrt(annualization))
        return result if math.isfinite(result) else 0.0

    def calculate_max_drawdown(self, equity_curve: list[Any]) -> float:
        """Calculate maximum drawdown from an equity curve.

        Maximum drawdown is the maximum peak-to-trough decline
        as a percentage of peak value.

        Args:
            equity_curve: List of portfolio values over time.

        Returns:
            Maximum drawdown as negative decimal (e.g., -0.15 for -15%).
            Returns 0.0 if insufficient data.

        Formula:
            MDD = (Trough - Peak) / Peak
        """
        self._last_calculation_source = self.MANUAL_SOURCE
        if len(equity_curve) < 2:
            return 0.0

        import numpy as np

        fincore_returns = self._fincore_equity_returns(equity_curve)
        if fincore_returns is not None:

            def calculate_with_fincore() -> Any:
                from fincore.metrics.drawdown import max_drawdown

                return max_drawdown(fincore_returns)

            fincore_result = self._try_fincore(calculate_with_fincore)
            if fincore_result is not None:
                return fincore_result

        equity_array = self._as_finite_array(equity_curve)
        if equity_array is None:
            return 0.0
        peak = np.maximum.accumulate(equity_array)
        with np.errstate(divide="ignore", invalid="ignore"):
            drawdown = (equity_array - peak) / peak
        result = float(np.nanmin(drawdown))
        return result if math.isfinite(result) else 0.0

    def calculate_total_returns(self, equity_curve: list[Any]) -> float:
        """Calculate total returns from initial to final value.

        Args:
            equity_curve: List of portfolio values over time.

        Returns:
            Total return as decimal (e.g., 0.15 for 15%).
            Returns 0.0 if insufficient data.

        Formula:
            Total Return = (Final Value - Initial Value) / Initial Value
        """
        self._last_calculation_source = self.MANUAL_SOURCE
        if len(equity_curve) < 2:
            return 0.0

        fincore_returns = self._fincore_equity_returns(equity_curve)
        if fincore_returns is not None:

            def calculate_with_fincore() -> Any:
                from fincore.metrics.returns import cum_returns_final

                return cum_returns_final(fincore_returns)

            fincore_result = self._try_fincore(calculate_with_fincore)
            if fincore_result is not None:
                return fincore_result

        values = self._as_finite_array(equity_curve)
        if values is None:
            return 0.0
        initial_value = values[0]
        final_value = values[-1]

        if initial_value == 0:
            return 0.0

        return float((final_value - initial_value) / initial_value)

    def calculate_annual_returns(
        self,
        equity_curve: list[Any],
        periods_per_year: float = 252.0,
    ) -> float:
        """Calculate annualized returns.

        Args:
            equity_curve: List of portfolio values over time.
            periods_per_year: Number of trading periods per year.
                              Defaults to 252 (trading days).

        Returns:
            Annualized return as decimal (e.g., 0.12 for 12%).
            Returns 0.0 if insufficient data.

        Formula:
            Annual Return = (Final / Initial)^(periods_per_year / n) - 1
            where n is the number of periods
        """
        self._last_calculation_source = self.MANUAL_SOURCE
        if len(equity_curve) < 2:
            return 0.0

        annualization = self._periods_per_year(periods_per_year)
        fincore_returns = self._fincore_equity_returns(equity_curve)
        if fincore_returns is not None:

            def calculate_with_fincore() -> Any:
                from fincore.metrics.yearly import annual_return

                return annual_return(fincore_returns, annualization=annualization)

            fincore_result = self._try_fincore(calculate_with_fincore)
            if fincore_result is not None:
                return fincore_result

        values = self._as_finite_array(equity_curve)
        if values is None:
            return 0.0
        initial_value = values[0]
        final_value = values[-1]
        periods = len(values) - 1

        if initial_value <= 0 or periods <= 0:
            return 0.0

        if final_value <= 0:
            return -1.0

        try:
            annualized_return = (final_value / initial_value) ** (annualization / periods) - 1
        except (OverflowError, ValueError, ZeroDivisionError):
            return 0.0

        return float(annualized_return) if math.isfinite(annualized_return) else 0.0

    def calculate_win_rate(self, trades: list) -> float:
        """Calculate win rate from a list of trades.

        Win rate is the percentage of profitable trades.
        Note: fincore library doesn't have a win_rate function, so this
        always uses manual calculation regardless of use_fincore setting.

        Args:
            trades: List of trade records, each containing 'pnlcomm' field
                    (profit/loss after commission).

        Returns:
            Win rate as decimal (e.g., 0.55 for 55%).
            Returns 0.0 if no trades provided.

        Formula:
            Win Rate = Winning Trades / Total Trades
        """
        if not trades:
            return 0.0

        # Manual calculation (fincore doesn't have win_rate function)
        closed_trades = [
            t for t in trades if t.get("pnlcomm") is not None or t.get("pnl") is not None
        ]
        winning_trades = sum(1 for t in closed_trades if t.get("pnlcomm", t.get("pnl", 0)) > 0)
        total_trades = len(closed_trades)

        if total_trades == 0:
            return 0.0

        return float(winning_trades / total_trades)

    def calculate_profit_factor(self, trades: list) -> float:
        """Calculate profit factor (ratio of average win to average loss).

        Args:
            trades: List of trade records, each containing 'pnlcomm' field
                    (profit/loss after commission).

        Returns:
            Profit factor as float. Returns 0.0 if no losses or no trades.
        """
        if not trades:
            return 0.0

        winning_trades = [t for t in trades if t.get("pnlcomm", 0) > 0]
        losing_trades = [t for t in trades if t.get("pnlcomm", 0) < 0]

        if not losing_trades or not winning_trades:
            return 0.0

        avg_win = sum(t.get("pnlcomm", 0) for t in winning_trades) / len(winning_trades)
        avg_loss = abs(sum(t.get("pnlcomm", 0) for t in losing_trades) / len(losing_trades))

        if avg_loss == 0:
            return 0.0

        return float(avg_win / avg_loss)

    def calculate_avg_holding_period(self, trades: list) -> float:
        """Calculate average holding period in days.

        Args:
            trades: List of trade records, each containing 'barlen' field
                    (number of bars the position was held).

        Returns:
            Average holding period in days. Returns 0.0 if no trades.
        """
        if not trades:
            return 0.0

        holding_periods = [
            float(t.get("barlen", 0))
            for t in trades
            if t.get("barlen") is not None and float(t.get("barlen", 0) or 0) > 0
        ]
        if not holding_periods:
            holding_periods = [
                holding_days
                for trade in trades
                if (holding_days := self._trade_holding_days(trade)) is not None
            ]

        if not holding_periods:
            return 0.0

        return float(sum(holding_periods) / len(holding_periods))

    @staticmethod
    def _parse_trade_datetime(value: Any) -> datetime.datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            return datetime.datetime.fromisoformat(text)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(text[: len(fmt)], fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def _trade_holding_days(cls, trade: dict[str, Any]) -> float | None:
        opened = cls._parse_trade_datetime(
            trade.get("dtopen")
            or trade.get("open_datetime")
            or trade.get("opened_at")
            or trade.get("entry_datetime")
            or trade.get("entry_date")
        )
        closed = cls._parse_trade_datetime(
            trade.get("dtclose")
            or trade.get("close_datetime")
            or trade.get("closed_at")
            or trade.get("exit_datetime")
            or trade.get("exit_date")
            or trade.get("datetime")
            or trade.get("date")
        )
        if opened is None or closed is None:
            return None
        if (opened.tzinfo is None) != (closed.tzinfo is None):
            opened = opened.replace(tzinfo=None)
            closed = closed.replace(tzinfo=None)
        seconds = (closed - opened).total_seconds()
        if seconds < 0:
            return None
        return seconds / 86400.0

    def calculate_max_consecutive(self, trades: list, win: bool) -> int:
        """Calculate maximum consecutive wins or losses.

        Args:
            trades: List of trade records, each containing 'pnlcomm' field.
            win: True to count consecutive wins, False for consecutive losses.

        Returns:
            Maximum consecutive count.
        """
        max_count = 0
        current = 0

        for t in trades:
            pnl = t.get("pnlcomm", 0)
            if pnl == 0:
                current = 0
                continue
            is_win = pnl > 0
            if is_win == win:
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0

        return max_count

    def calculate_max_drawdown_with_duration(self, equity_curve: list) -> tuple:
        """Calculate maximum drawdown and its duration.

        Args:
            equity_curve: List of portfolio values over time.

        Returns:
            Tuple of (max_drawdown, duration_days).
        """
        if len(equity_curve) < 2:
            return 0.0, 0

        import numpy as np

        equity_array = np.array(equity_curve)
        peak = equity_array[0]
        max_dd = 0.0
        max_dd_duration = 0
        current_duration = 0

        for value in equity_array:
            if value > peak:
                peak = value
                current_duration = 0
            else:
                dd = (value - peak) / peak if peak > 0 else 0
                current_duration += 1
                if dd < max_dd:
                    max_dd = dd
                    max_dd_duration = current_duration

        return float(max_dd), max_dd_duration
