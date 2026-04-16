"""
Metrics API endpoint for Prometheus scraping.

Exposes /metrics endpoint for monitoring systems.
"""

from fastapi import APIRouter, Response
from fastapi.responses import PlainTextResponse

from app.middleware.metrics import get_metrics_output, is_metrics_available
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get(
    "/metrics",
    response_class=PlainTextResponse,
    summary="Prometheus metrics endpoint",
    description="Exposes metrics in Prometheus text format for monitoring and alerting.",
    responses={
        200: {
            "description": "Prometheus metrics in text format",
            "content": {
                "text/plain": {
                    "example": '# HELP backtest_total Total number of backtest tasks\n# TYPE backtest_total counter\nbacktest_total{status="completed"} 42\n'
                }
            },
        },
        503: {
            "description": "Metrics unavailable (prometheus_client not installed)",
        },
    },
)
async def metrics_endpoint() -> Response:
    """Get Prometheus metrics.

    Returns:
        Prometheus text format metrics.

    Raises:
        HTTPException: If metrics collection is not available.
    """
    if not is_metrics_available():
        return Response(
            content="# Metrics unavailable: prometheus_client not installed\n"
            "# Install with: pip install prometheus_client\n",
            status_code=503,
            media_type="text/plain",
        )

    try:
        metrics_output = get_metrics_output()
        return Response(content=metrics_output, media_type="text/plain")
    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        return Response(
            content=f"# Error generating metrics: {e}\n",
            status_code=500,
            media_type="text/plain",
        )


@router.get(
    "/metrics/status",
    summary="Metrics collection status",
    description="Returns the status of metrics collection.",
)
async def metrics_status() -> dict:
    """Get metrics collection status.

    Returns:
        Status information about metrics collection.
    """
    return {
        "available": is_metrics_available(),
        "backend": "prometheus_client" if is_metrics_available() else None,
        "metrics": [
            "backtest_total",
            "backtest_duration_seconds",
            "backtest_success_total",
            "backtest_failure_total",
            "live_trading_active_instances",
            "live_trading_total_trades",
            "api_request_total",
            "api_request_duration_seconds",
            "api_request_errors_total",
            "db_query_duration_seconds",
            "db_query_total",
            "error_total",
        ]
        if is_metrics_available()
        else [],
    }
