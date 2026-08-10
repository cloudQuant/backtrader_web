"""
Metrics collection module for business and system monitoring.

Provides Prometheus-compatible metrics for:
- Backtest execution duration and count
- Live trading instance status
- API request latency
- Database query performance
"""

import re
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Protocol

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

_prometheus_client: Any
try:
    import prometheus_client as _prometheus_client

    PROMETHEUS_AVAILABLE = True
except ImportError:
    _prometheus_client = None
    PROMETHEUS_AVAILABLE = False

# Create a custom registry to avoid conflicts
_registry: Any = _prometheus_client.CollectorRegistry() if PROMETHEUS_AVAILABLE else None

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

# Asset-research metrics.  Labels are deliberately constrained here because
# this registry is scraped globally; symbols, users, tasks and URLs belong in
# protected logs/traces, never in Prometheus label values.
ASSET_RESEARCH_TASK_TOTAL: MetricCounter = None
ASSET_RESEARCH_TASK_DURATION: MetricHistogram = None
ASSET_RESEARCH_SOURCE_REQUEST_TOTAL: MetricCounter = None
ASSET_RESEARCH_SOURCE_DURATION: MetricHistogram = None
ASSET_RESEARCH_SCHEDULE_RUN_TOTAL: MetricCounter = None
ASSET_RESEARCH_SCHEDULE_LATENESS: MetricHistogram = None
ASSET_RESEARCH_PREDICTION_REUSE_TOTAL: MetricCounter = None
ASSET_RESEARCH_OUTCOME_TOTAL: MetricCounter = None
ASSET_RESEARCH_OUTCOME_BACKLOG: MetricGauge = None
ASSET_RESEARCH_QUEUE_DEPTH: MetricGauge = None
ASSET_RESEARCH_LIFECYCLE_TOTAL: MetricCounter = None
ASSET_RESEARCH_EXPORT_TOTAL: MetricCounter = None
ASSET_RESEARCH_PUBLICATION_TOTAL: MetricCounter = None
ASSET_RESEARCH_LLM_TOKENS_TOTAL: MetricCounter = None
ASSET_RESEARCH_LLM_COST_USD_TOTAL: MetricCounter = None
ASSET_RESEARCH_LLM_FALLBACK_TOTAL: MetricCounter = None
ASSET_RESEARCH_MIGRATION_RECONCILIATION_TOTAL: MetricCounter = None

_ASSET_TYPES = frozenset({"stock", "bond", "fund", "futures", "option", "fx", "crypto"})
_TASK_STATUSES = frozenset({"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"})
_SOURCE_RESULTS = frozenset({"AUTHORIZED", "BLOCKED", "FAILED", "UNREGISTERED"})
_OUTCOME_STATUSES = frozenset({"PENDING", "PARTIAL", "SCORED", "UNSCORABLE"})
_ARTIFACT_STATUSES = frozenset({"SUCCEEDED", "FAILED"})
_EXPORT_FORMATS = frozenset({"MARKDOWN", "PDF"})
_PUBLICATION_TARGETS = frozenset({"KNOWLEDGE_BASE", "WORKSPACE"})
_SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_LLM_STAGES = frozenset({"REPORT", "SUMMARIZE", "RETRY", "TOTAL"})
_MODEL_TIERS = frozenset({"DEFAULT", "ECONOMY", "PREMIUM"})
_FALLBACK_REASONS = frozenset(
    {"BUDGET", "RATE_LIMIT", "TIMEOUT", "OUTPUT_INVALID", "MODEL_UNAVAILABLE"}
)
_MIGRATION_CLASSIFICATIONS = frozenset(
    {
        "EXPECTED_MAPPING",
        "NONDETERMINISTIC_PRESENTATION",
        "SOURCE_OR_TIMING",
        "DEFECT",
    }
)
_MAPPING_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _init_metrics() -> None:
    """Initialize all metrics. Called lazily on first use."""
    global BACKTEST_TOTAL, BACKTEST_DURATION, BACKTEST_SUCCESS, BACKTEST_FAILURE
    global LIVE_TRADING_ACTIVE_INSTANCES, LIVE_TRADING_TOTAL_TRADES
    global API_REQUEST_TOTAL, API_REQUEST_DURATION, API_REQUEST_ERRORS
    global DB_QUERY_DURATION, DB_QUERY_TOTAL, ERROR_TOTAL
    global ASSET_RESEARCH_TASK_TOTAL, ASSET_RESEARCH_TASK_DURATION
    global ASSET_RESEARCH_SOURCE_REQUEST_TOTAL, ASSET_RESEARCH_SOURCE_DURATION
    global ASSET_RESEARCH_SCHEDULE_RUN_TOTAL, ASSET_RESEARCH_SCHEDULE_LATENESS
    global ASSET_RESEARCH_PREDICTION_REUSE_TOTAL, ASSET_RESEARCH_OUTCOME_TOTAL
    global ASSET_RESEARCH_OUTCOME_BACKLOG, ASSET_RESEARCH_LIFECYCLE_TOTAL
    global ASSET_RESEARCH_EXPORT_TOTAL, ASSET_RESEARCH_PUBLICATION_TOTAL
    global ASSET_RESEARCH_QUEUE_DEPTH, ASSET_RESEARCH_LLM_TOKENS_TOTAL
    global ASSET_RESEARCH_LLM_COST_USD_TOTAL, ASSET_RESEARCH_LLM_FALLBACK_TOTAL
    global ASSET_RESEARCH_MIGRATION_RECONCILIATION_TOTAL

    if not PROMETHEUS_AVAILABLE or _registry is None:
        return

    # Backtest metrics
    BACKTEST_TOTAL = _prometheus_client.Counter(
        "backtest_total",
        "Total number of backtest tasks",
        ["status"],  # pending, running, completed, failed, cancelled
        registry=_registry,
    )

    BACKTEST_DURATION = _prometheus_client.Histogram(
        "backtest_duration_seconds",
        "Duration of backtest execution in seconds",
        ["strategy_id"],
        buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 3600],
        registry=_registry,
    )

    BACKTEST_SUCCESS = _prometheus_client.Counter(
        "backtest_success_total",
        "Number of successful backtests",
        registry=_registry,
    )

    BACKTEST_FAILURE = _prometheus_client.Counter(
        "backtest_failure_total",
        "Number of failed backtests",
        registry=_registry,
    )

    # Live trading metrics
    LIVE_TRADING_ACTIVE_INSTANCES = _prometheus_client.Gauge(
        "live_trading_active_instances",
        "Number of active live trading instances",
        ["broker"],
        registry=_registry,
    )

    LIVE_TRADING_TOTAL_TRADES = _prometheus_client.Counter(
        "live_trading_total_trades",
        "Total number of live trading trades executed",
        ["broker", "symbol"],
        registry=_registry,
    )

    # API metrics
    API_REQUEST_TOTAL = _prometheus_client.Counter(
        "api_request_total",
        "Total number of API requests",
        ["method", "endpoint", "status_code"],
        registry=_registry,
    )

    API_REQUEST_DURATION = _prometheus_client.Histogram(
        "api_request_duration_seconds",
        "Duration of API request processing in seconds",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
        registry=_registry,
    )

    API_REQUEST_ERRORS = _prometheus_client.Counter(
        "api_request_errors_total",
        "Total number of API request errors",
        ["method", "endpoint", "error_type"],
        registry=_registry,
    )

    # Database metrics
    DB_QUERY_DURATION = _prometheus_client.Histogram(
        "db_query_duration_seconds",
        "Duration of database queries in seconds",
        ["operation"],  # select, insert, update, delete
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1],
        registry=_registry,
    )

    DB_QUERY_TOTAL = _prometheus_client.Counter(
        "db_query_total",
        "Total number of database queries",
        ["operation", "table"],
        registry=_registry,
    )

    # Error metrics
    ERROR_TOTAL = _prometheus_client.Counter(
        "error_total",
        "Total number of errors",
        ["type", "module"],
        registry=_registry,
    )

    # Multi-asset research metrics.  These are intentionally business-level
    # counters/gauges, not a replacement for existing request or AI metrics.
    ASSET_RESEARCH_TASK_TOTAL = _prometheus_client.Counter(
        "asset_research_task_total",
        "Total multi-asset research tasks by terminal or lifecycle status",
        ["asset_type", "status"],
        registry=_registry,
    )
    ASSET_RESEARCH_TASK_DURATION = _prometheus_client.Histogram(
        "asset_research_task_duration_seconds",
        "Duration of completed multi-asset research tasks",
        ["asset_type"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300],
        registry=_registry,
    )
    ASSET_RESEARCH_SOURCE_REQUEST_TOTAL = _prometheus_client.Counter(
        "asset_research_source_request_total",
        "Authorized multi-asset source collection attempts",
        ["source_id", "result"],
        registry=_registry,
    )
    ASSET_RESEARCH_SOURCE_DURATION = _prometheus_client.Histogram(
        "asset_research_source_duration_seconds",
        "Duration of multi-asset source collection attempts",
        ["source_id"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
        registry=_registry,
    )
    ASSET_RESEARCH_SCHEDULE_RUN_TOTAL = _prometheus_client.Counter(
        "asset_research_schedule_run_total",
        "Total multi-asset shadow schedule runs",
        ["asset_type", "status"],
        registry=_registry,
    )
    ASSET_RESEARCH_SCHEDULE_LATENESS = _prometheus_client.Histogram(
        "asset_research_schedule_lateness_seconds",
        "Lateness between scheduled fire and multi-asset schedule completion",
        ["asset_type"],
        buckets=[0, 1, 5, 15, 30, 60, 300, 900, 3600],
        registry=_registry,
    )
    ASSET_RESEARCH_PREDICTION_REUSE_TOTAL = _prometheus_client.Counter(
        "asset_research_prediction_reuse_total",
        "Number of reused immutable multi-asset predictions",
        ["asset_type"],
        registry=_registry,
    )
    ASSET_RESEARCH_OUTCOME_TOTAL = _prometheus_client.Counter(
        "asset_research_outcome_total",
        "Multi-asset outcome heads by scoring status",
        ["asset_type", "status"],
        registry=_registry,
    )
    ASSET_RESEARCH_OUTCOME_BACKLOG = _prometheus_client.Gauge(
        "asset_research_outcome_backlog",
        "Mature multi-asset outcome heads awaiting evaluation",
        ["asset_type"],
        registry=_registry,
    )
    ASSET_RESEARCH_LIFECYCLE_TOTAL = _prometheus_client.Counter(
        "asset_research_lifecycle_total",
        "Multi-asset research retention dry-run lifecycle results",
        ["retention_class", "result"],
        registry=_registry,
    )
    ASSET_RESEARCH_EXPORT_TOTAL = _prometheus_client.Counter(
        "asset_research_export_total",
        "Multi-asset research report exports by bounded format and terminal status",
        ["format", "status"],
        registry=_registry,
    )
    ASSET_RESEARCH_PUBLICATION_TOTAL = _prometheus_client.Counter(
        "asset_research_publication_total",
        "Multi-asset research report publications by bounded target and terminal status",
        ["target", "status"],
        registry=_registry,
    )
    ASSET_RESEARCH_QUEUE_DEPTH = _prometheus_client.Gauge(
        "asset_research_queue_depth",
        "Current multi-asset research queue depth by bounded asset class",
        ["asset_type"],
        registry=_registry,
    )
    ASSET_RESEARCH_LLM_TOKENS_TOTAL = _prometheus_client.Counter(
        "asset_research_llm_tokens_total",
        "Multi-asset LLM tokens by bounded stage and model tier",
        ["asset_type", "stage", "model_tier"],
        registry=_registry,
    )
    ASSET_RESEARCH_LLM_COST_USD_TOTAL = _prometheus_client.Counter(
        "asset_research_llm_cost_usd_total",
        "Multi-asset LLM cost in USD by bounded stage and model tier",
        ["asset_type", "stage", "model_tier"],
        registry=_registry,
    )
    ASSET_RESEARCH_LLM_FALLBACK_TOTAL = _prometheus_client.Counter(
        "asset_research_llm_fallback_total",
        "Multi-asset LLM fallback events by bounded stage and reason",
        ["asset_type", "fallback_stage", "reason"],
        registry=_registry,
    )
    ASSET_RESEARCH_MIGRATION_RECONCILIATION_TOTAL = _prometheus_client.Counter(
        "asset_research_migration_reconciliation_total",
        "Multi-asset stock compatibility reconciliation rows by classification",
        ["mapping_version", "classification"],
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

    return _prometheus_client.generate_latest(_registry).decode("utf-8")


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


def _ensure_asset_research_metrics() -> bool:
    """Lazily initialize the shared registry before emitting a bounded metric."""
    if not PROMETHEUS_AVAILABLE:
        return False
    if ASSET_RESEARCH_TASK_TOTAL is None:
        _init_metrics()
    return ASSET_RESEARCH_TASK_TOTAL is not None


def _asset_type_label(asset_type: str) -> str:
    normalized = str(asset_type).lower()
    return normalized if normalized in _ASSET_TYPES else "unknown"


def _bounded_status(value: str, allowed: frozenset[str]) -> str:
    normalized = str(value).upper()
    return normalized if normalized in allowed else "UNKNOWN"


def _source_id_label(source_id: str) -> str:
    """Accept only compact registry IDs; never expose a provider URL or query."""
    candidate = str(source_id).strip()
    return candidate if _SOURCE_ID_PATTERN.fullmatch(candidate) else "UNREGISTERED"


def _retention_class_label(retention_class: str) -> str:
    """Keep lifecycle label cardinality under the versioned retention namespace."""
    candidate = str(retention_class).strip()
    return candidate if re.fullmatch(r"research-v[0-9]+", candidate) else "unknown"


def record_asset_research_task(
    *, asset_type: str, status: str, duration_seconds: float | None = None
) -> None:
    """Record one task lifecycle transition and an optional completed duration."""
    if not _ensure_asset_research_metrics():
        return
    label = _asset_type_label(asset_type)
    if ASSET_RESEARCH_TASK_TOTAL is not None:
        ASSET_RESEARCH_TASK_TOTAL.labels(
            asset_type=label,
            status=_bounded_status(status, _TASK_STATUSES),
        ).inc()
    if duration_seconds is not None and duration_seconds >= 0 and ASSET_RESEARCH_TASK_DURATION is not None:
        ASSET_RESEARCH_TASK_DURATION.labels(asset_type=label).observe(duration_seconds)


def record_asset_research_source(
    *,
    source_id: str,
    result: str,
    duration_seconds: float | None = None,
    registered: bool = False,
) -> None:
    """Record one source call using only a server-registry-compatible source label.

    ``registered`` is deliberately explicit: a compact-looking provider string
    alone is not authorization to create a Prometheus label value.
    """
    if not _ensure_asset_research_metrics():
        return
    label = _source_id_label(source_id) if registered else "UNREGISTERED"
    if ASSET_RESEARCH_SOURCE_REQUEST_TOTAL is not None:
        ASSET_RESEARCH_SOURCE_REQUEST_TOTAL.labels(
            source_id=label,
            result=_bounded_status(result, _SOURCE_RESULTS),
        ).inc()
    if duration_seconds is not None and duration_seconds >= 0 and ASSET_RESEARCH_SOURCE_DURATION is not None:
        ASSET_RESEARCH_SOURCE_DURATION.labels(source_id=label).observe(duration_seconds)


def record_asset_research_schedule_run(
    *, asset_type: str, status: str, lateness_seconds: float | None = None
) -> None:
    """Record a bounded schedule result and optional completion lateness."""
    if not _ensure_asset_research_metrics():
        return
    label = _asset_type_label(asset_type)
    if ASSET_RESEARCH_SCHEDULE_RUN_TOTAL is not None:
        ASSET_RESEARCH_SCHEDULE_RUN_TOTAL.labels(
            asset_type=label,
            status=_bounded_status(status, _TASK_STATUSES),
        ).inc()
    if (
        lateness_seconds is not None
        and lateness_seconds >= 0
        and ASSET_RESEARCH_SCHEDULE_LATENESS is not None
    ):
        ASSET_RESEARCH_SCHEDULE_LATENESS.labels(asset_type=label).observe(lateness_seconds)


def record_asset_research_prediction_reuse(*, asset_type: str) -> None:
    """Record a deterministic prediction reuse without a prediction identifier label."""
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_PREDICTION_REUSE_TOTAL is not None:
        ASSET_RESEARCH_PREDICTION_REUSE_TOTAL.labels(asset_type=_asset_type_label(asset_type)).inc()


def record_asset_research_outcome(*, asset_type: str, status: str) -> None:
    """Record an outcome-head scoring state for one bounded asset class."""
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_OUTCOME_TOTAL is not None:
        ASSET_RESEARCH_OUTCOME_TOTAL.labels(
            asset_type=_asset_type_label(asset_type),
            status=_bounded_status(status, _OUTCOME_STATUSES),
        ).inc()


def set_asset_research_outcome_backlog(*, asset_type: str, count: int) -> None:
    """Set the mature outcome backlog; negative counts are clamped to zero."""
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_OUTCOME_BACKLOG is not None:
        ASSET_RESEARCH_OUTCOME_BACKLOG.labels(asset_type=_asset_type_label(asset_type)).set(
            max(0, count)
        )


def set_asset_research_queue_depth(*, asset_type: str, count: int) -> None:
    """Set the current research queue depth without a queue or task identifier label."""
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_QUEUE_DEPTH is not None:
        ASSET_RESEARCH_QUEUE_DEPTH.labels(asset_type=_asset_type_label(asset_type)).set(
            max(0, count)
        )


def _bounded_enum(value: str, allowed: frozenset[str]) -> str:
    normalized = str(value).upper()
    return normalized if normalized in allowed else "UNKNOWN"


def _mapping_version_label(value: str) -> str:
    candidate = str(value).strip()
    return candidate if _MAPPING_VERSION_PATTERN.fullmatch(candidate) else "UNKNOWN"


def record_asset_research_llm_tokens(
    *, asset_type: str, stage: str, model_tier: str, tokens: int
) -> None:
    """Record LLM tokens with only bounded asset, stage and model-tier labels."""
    if tokens <= 0 or not _ensure_asset_research_metrics():
        return
    if ASSET_RESEARCH_LLM_TOKENS_TOTAL is not None:
        ASSET_RESEARCH_LLM_TOKENS_TOTAL.labels(
            asset_type=_asset_type_label(asset_type),
            stage=_bounded_enum(stage, _LLM_STAGES),
            model_tier=_bounded_enum(model_tier, _MODEL_TIERS),
        ).inc(int(tokens))


def record_asset_research_llm_cost_usd(
    *, asset_type: str, stage: str, model_tier: str, cost_usd: float
) -> None:
    """Record LLM cost without exposing provider-specific pricing or request IDs."""
    if cost_usd <= 0 or not _ensure_asset_research_metrics():
        return
    if ASSET_RESEARCH_LLM_COST_USD_TOTAL is not None:
        ASSET_RESEARCH_LLM_COST_USD_TOTAL.labels(
            asset_type=_asset_type_label(asset_type),
            stage=_bounded_enum(stage, _LLM_STAGES),
            model_tier=_bounded_enum(model_tier, _MODEL_TIERS),
        ).inc(float(cost_usd))


def record_asset_research_llm_fallback(
    *, asset_type: str, fallback_stage: str, reason: str
) -> None:
    """Record one controlled LLM fallback event for alerting and budget review."""
    if not _ensure_asset_research_metrics():
        return
    if ASSET_RESEARCH_LLM_FALLBACK_TOTAL is not None:
        ASSET_RESEARCH_LLM_FALLBACK_TOTAL.labels(
            asset_type=_asset_type_label(asset_type),
            fallback_stage=_bounded_enum(fallback_stage, _LLM_STAGES),
            reason=_bounded_enum(reason, _FALLBACK_REASONS),
        ).inc()


def record_asset_research_migration_reconciliation(
    *, mapping_version: str, classification: str
) -> None:
    """Record one structured reconciliation classification with a versioned mapping label."""
    if not _ensure_asset_research_metrics():
        return
    if ASSET_RESEARCH_MIGRATION_RECONCILIATION_TOTAL is not None:
        ASSET_RESEARCH_MIGRATION_RECONCILIATION_TOTAL.labels(
            mapping_version=_mapping_version_label(mapping_version),
            classification=_bounded_enum(
                classification, _MIGRATION_CLASSIFICATIONS
            ),
        ).inc()


def record_asset_research_lifecycle(
    *, retention_class: str, result: str, amount: int = 1
) -> None:
    """Record a dry-run lifecycle classification without a record or tenant label."""
    if amount <= 0:
        return
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_LIFECYCLE_TOTAL is not None:
        ASSET_RESEARCH_LIFECYCLE_TOTAL.labels(
            retention_class=_retention_class_label(retention_class),
            result=_bounded_status(result, frozenset({"ELIGIBLE", "HELD", "TOMBSTONED"})),
        ).inc(amount)


def record_asset_research_export(*, export_format: str, status: str) -> None:
    """Record an export terminal state without exposing a report or storage identifier."""
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_EXPORT_TOTAL is not None:
        normalized_format = str(export_format).upper()
        ASSET_RESEARCH_EXPORT_TOTAL.labels(
            format=normalized_format if normalized_format in _EXPORT_FORMATS else "UNKNOWN",
            status=_bounded_status(status, _ARTIFACT_STATUSES),
        ).inc()


def record_asset_research_publication(*, target_type: str, status: str) -> None:
    """Record a publication terminal state without exposing target or tenant identifiers."""
    if _ensure_asset_research_metrics() and ASSET_RESEARCH_PUBLICATION_TOTAL is not None:
        normalized_target = str(target_type).upper()
        ASSET_RESEARCH_PUBLICATION_TOTAL.labels(
            target=normalized_target if normalized_target in _PUBLICATION_TARGETS else "UNKNOWN",
            status=_bounded_status(status, _ARTIFACT_STATUSES),
        ).inc()


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
    "record_asset_research_task",
    "record_asset_research_source",
    "record_asset_research_schedule_run",
    "record_asset_research_prediction_reuse",
    "record_asset_research_outcome",
    "set_asset_research_outcome_backlog",
    "set_asset_research_queue_depth",
    "record_asset_research_llm_tokens",
    "record_asset_research_llm_cost_usd",
    "record_asset_research_llm_fallback",
    "record_asset_research_migration_reconciliation",
    "record_asset_research_lifecycle",
    "record_asset_research_export",
    "record_asset_research_publication",
    "track_db_query",
    "track_api_request",
]
