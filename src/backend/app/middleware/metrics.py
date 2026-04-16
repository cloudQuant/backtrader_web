"""
Metrics collection module for business and system monitoring.

Provides Prometheus-compatible metrics for:
- Backtest execution duration and count
- Live trading instance status
- API request latency
- Database query performance
"""

import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Protocol

from loguru import logger


# Type aliases for Prometheus metrics
class CounterProtocol(Protocol):
    """Protocol for Prometheus Counter metric."""

    def labels(self, **kwargs: str) -> "CounterProtocol": ...
    def inc(self, amount: float = 1.0) -> None: ...


class GaugeProtocol(Protocol):
    """Protocol for Prometheus Gauge metric."""

    def labels(self, **kwargs: str) -> "GaugeProtocol": ...
    def set(self, value: float) -> None: ...
    def inc(self, amount: float = 1.0) -> None: ...
    def dec(self, amount: float = 1.0) -> None: ...


class HistogramProtocol(Protocol):
    """Protocol for Prometheus Histogram metric."""

    def labels(self, **kwargs: str) -> "HistogramProtocol": ...
    def observe(self, amount: float) -> None: ...


# Type aliases for metrics
MetricCounter = CounterProtocol | None
MetricGauge = GaugeProtocol | None
MetricHistogram = HistogramProtocol | None

# Try to import prometheus_client, fall back to no-op if not available
try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
    from prometheus_client import CollectorRegistry as RegistryType
    from prometheus_client import Counter as CounterType
    from prometheus_client import Gauge as GaugeType
    from prometheus_client import Histogram as HistogramType

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    Counter = None
    Histogram = None
    Gauge = None
    CollectorRegistry = None
    generate_latest = None
    CounterType = None  # type: ignore[misc,assignment]
    HistogramType = None  # type: ignore[misc,assignment]
    GaugeType = None  # type: ignore[misc,assignment]
    RegistryType = None  # type: ignore[misc,assignment]

# Create a custom registry to avoid conflicts
_registry: RegistryType = CollectorRegistry() if PROMETHEUS_AVAILABLE else None

# ==================== Business Metrics ====================

# Backtest metrics
BACKTEST_TOTAL: MetricCounter = None
BACKTEST_DURATION: MetricHistogram = None
BACKTEST_SUCCESS: MetricCounter = None
BACKTEST_FAILURE: MetricCounter = None

# Live trading metrics
LIVE_TRADING_ACTIVE_INSTANCES: MetricGauge = None
LIVE_TRADING_TOTAL_TRADES: MetricCounter = None

# ==================== System Metrics ====================

# API metrics
API_REQUEST_TOTAL: MetricCounter = None
API_REQUEST_DURATION: MetricHistogram = None
API_REQUEST_ERRORS: MetricCounter = None

# Database metrics
DB_QUERY_DURATION: MetricHistogram = None
DB_QUERY_TOTAL: MetricCounter = None

# Error metrics
ERROR_TOTAL: MetricCounter = None


def _init_metrics() -> None:
    """Initialize all metrics. Called lazily on first use."""
    global BACKTEST_TOTAL, BACKTEST_DURATION, BACKTEST_SUCCESS, BACKTEST_FAILURE
    global LIVE_TRADING_ACTIVE_INSTANCES, LIVE_TRADING_TOTAL_TRADES
    global API_REQUEST_TOTAL, API_REQUEST_DURATION, API_REQUEST_ERRORS
    global DB_QUERY_DURATION, DB_QUERY_TOTAL, ERROR_TOTAL

    if not PROMETHEUS_AVAILABLE or _registry is None:
        return

    # Backtest metrics
    BACKTEST_TOTAL = Counter(
        "backtest_total",
        "Total number of backtest tasks",
        ["status"],  # pending, running, completed, failed, cancelled
        registry=_registry,
    )

    BACKTEST_DURATION = Histogram(
        "backtest_duration_seconds",
        "Duration of backtest execution in seconds",
        ["strategy_id"],
        buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 3600],
        registry=_registry,
    )

    BACKTEST_SUCCESS = Counter(
        "backtest_success_total",
        "Number of successful backtests",
        registry=_registry,
    )

    BACKTEST_FAILURE = Counter(
        "backtest_failure_total",
        "Number of failed backtests",
        registry=_registry,
    )

    # Live trading metrics
    LIVE_TRADING_ACTIVE_INSTANCES = Gauge(
        "live_trading_active_instances",
        "Number of active live trading instances",
        ["broker"],
        registry=_registry,
    )

    LIVE_TRADING_TOTAL_TRADES = Counter(
        "live_trading_total_trades",
        "Total number of live trading trades executed",
        ["broker", "symbol"],
        registry=_registry,
    )

    # API metrics
    API_REQUEST_TOTAL = Counter(
        "api_request_total",
        "Total number of API requests",
        ["method", "endpoint", "status_code"],
        registry=_registry,
    )

    API_REQUEST_DURATION = Histogram(
        "api_request_duration_seconds",
        "Duration of API request processing in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
        registry=_registry,
    )

    API_REQUEST_ERRORS = Counter(
        "api_request_errors_total",
        "Total number of API request errors",
        ["method", "endpoint", "error_type"],
        registry=_registry,
    )

    # Database metrics
    DB_QUERY_DURATION = Histogram(
        "db_query_duration_seconds",
        "Duration of database queries in seconds",
        ["operation"],  # select, insert, update, delete
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
        registry=_registry,
    )

    DB_QUERY_TOTAL = Counter(
        "db_query_total",
        "Total number of database queries",
        ["operation", "table"],
        registry=_registry,
    )

    # Error metrics
    ERROR_TOTAL = Counter(
        "error_total",
        "Total number of errors",
        ["type", "module"],
        registry=_registry,
    )


def is_metrics_available() -> bool:
    """Check if metrics collection is available."""
    return PROMETHEUS_AVAILABLE


def get_metrics_output() -> str:
    """Get Prometheus metrics output.

    Returns:
        Prometheus text format metrics string.

    Raises:
        RuntimeError: If prometheus_client is not installed.
    """
    if not PROMETHEUS_AVAILABLE or _registry is None:
        raise RuntimeError(
            "prometheus_client is not installed. Install it with: pip install prometheus_client"
        )

    # Initialize metrics if not done
    if BACKTEST_TOTAL is None:
        _init_metrics()

    return generate_latest(_registry).decode("utf-8")


# ==================== Helper Functions ====================


def record_backtest_start(strategy_id: str) -> None:
    """Record the start of a backtest task.

    Args:
        strategy_id: The strategy identifier.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if BACKTEST_TOTAL is None:
        _init_metrics()

    if BACKTEST_TOTAL is not None:
        BACKTEST_TOTAL.labels(status="running").inc()


def record_backtest_complete(strategy_id: str, duration_seconds: float, success: bool) -> None:
    """Record the completion of a backtest task.

    Args:
        strategy_id: The strategy identifier.
        duration_seconds: Duration of the backtest in seconds.
        success: Whether the backtest completed successfully.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if BACKTEST_DURATION is None:
        _init_metrics()

    if BACKTEST_DURATION is not None:
        BACKTEST_DURATION.labels(strategy_id=strategy_id).observe(duration_seconds)

    if success:
        if BACKTEST_SUCCESS is not None:
            BACKTEST_SUCCESS.inc()
        if BACKTEST_TOTAL is not None:
            BACKTEST_TOTAL.labels(status="completed").inc()
    else:
        if BACKTEST_FAILURE is not None:
            BACKTEST_FAILURE.inc()
        if BACKTEST_TOTAL is not None:
            BACKTEST_TOTAL.labels(status="failed").inc()


def record_api_request(
    method: str, endpoint: str, status_code: int, duration_seconds: float
) -> None:
    """Record an API request.

    Args:
        method: HTTP method (GET, POST, etc.).
        endpoint: API endpoint path.
        status_code: HTTP response status code.
        duration_seconds: Request processing duration in seconds.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if API_REQUEST_TOTAL is None:
        _init_metrics()

    if API_REQUEST_TOTAL is not None:
        API_REQUEST_TOTAL.labels(
            method=method, endpoint=endpoint, status_code=str(status_code)
        ).inc()

    if API_REQUEST_DURATION is not None:
        API_REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration_seconds)


def record_api_error(method: str, endpoint: str, error_type: str) -> None:
    """Record an API request error.

    Args:
        method: HTTP method.
        endpoint: API endpoint path.
        error_type: Error type or exception name.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if API_REQUEST_ERRORS is None:
        _init_metrics()

    if API_REQUEST_ERRORS is not None:
        API_REQUEST_ERRORS.labels(method=method, endpoint=endpoint, error_type=error_type).inc()


def set_live_trading_instances(broker: str, count: int) -> None:
    """Set the number of active live trading instances for a broker.

    Args:
        broker: Broker identifier.
        count: Number of active instances.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if LIVE_TRADING_ACTIVE_INSTANCES is None:
        _init_metrics()

    if LIVE_TRADING_ACTIVE_INSTANCES is not None:
        LIVE_TRADING_ACTIVE_INSTANCES.labels(broker=broker).set(count)


def record_live_trade(broker: str, symbol: str) -> None:
    """Record a live trading trade execution.

    Args:
        broker: Broker identifier.
        symbol: Trading symbol.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if LIVE_TRADING_TOTAL_TRADES is None:
        _init_metrics()

    if LIVE_TRADING_TOTAL_TRADES is not None:
        LIVE_TRADING_TOTAL_TRADES.labels(broker=broker, symbol=symbol).inc()


def record_db_query(operation: str, table: str, duration_seconds: float) -> None:
    """Record a database query.

    Args:
        operation: Database operation (select, insert, update, delete).
        table: Table name.
        duration_seconds: Query duration in seconds.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if DB_QUERY_DURATION is None:
        _init_metrics()

    if DB_QUERY_DURATION is not None:
        DB_QUERY_DURATION.labels(operation=operation).observe(duration_seconds)

    if DB_QUERY_TOTAL is not None:
        DB_QUERY_TOTAL.labels(operation=operation, table=table).inc()


def record_error(error_type: str, module: str) -> None:
    """Record an error occurrence.

    Args:
        error_type: Error type or exception name.
        module: Module where the error occurred.
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if ERROR_TOTAL is None:
        _init_metrics()

    if ERROR_TOTAL is not None:
        ERROR_TOTAL.labels(type=error_type, module=module).inc()


@contextmanager
def track_db_query(operation: str, table: str) -> Generator[None, None, None]:
    """Context manager to track database query duration.

    Args:
        operation: Database operation type.
        table: Table name.

    Yields:
        None

    Example:
        with track_db_query('select', 'users'):
            result = await session.execute(query)
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        record_db_query(operation, table, duration)


@contextmanager
def track_api_request(method: str, endpoint: str) -> Generator[None, None, None]:
    """Context manager to track API request duration.

    Args:
        method: HTTP method.
        endpoint: API endpoint path.

    Yields:
        None

    Example:
        with track_api_request('GET', '/api/v1/backtests'):
            result = await service.list_backtests()
    """
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start_time
        # Status code will be recorded separately
        logger.debug(f"API request {method} {endpoint} took {duration:.3f}s")


__all__ = [
    "is_metrics_available",
    "get_metrics_output",
    "record_backtest_start",
    "record_backtest_complete",
    "record_api_request",
    "record_api_error",
    "set_live_trading_instances",
    "record_live_trade",
    "record_db_query",
    "record_error",
    "track_db_query",
    "track_api_request",
]
