"""
OpenTelemetry instrumentation (env-var gated).

Provides distributed tracing for HTTP requests, database queries, and outbound
HTTP calls. Enabled only when the ``OTEL_ENABLED`` environment variable is set
to ``true``, ``1``, or ``yes`` (case-insensitive).

Environment variables (standard OTEL SDK config):
    OTEL_ENABLED          - Set to "true"/"1"/"yes" to activate instrumentation.
    OTEL_SERVICE_NAME     - Logical service name (default: "ai-for-trader-api").
    OTEL_EXPORTER_OTLP_ENDPOINT - OTLP collector endpoint (default: http://localhost:4317).
    OTEL_TRACES_SAMPLER   - Sampler type (default: parentbased_tracealways).
    OTEL_LOG_LEVEL        - SDK internal log level (default: warning).

Usage:
    Call ``setup_telemetry(app)`` during application startup (in main.py lifespan
    or after app creation). If OTEL is disabled, the function is a no-op with
    zero overhead.

Example:
    from app.telemetry import setup_telemetry
    setup_telemetry(app)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_OTEL_INITIALIZED = False


def _is_otel_enabled() -> bool:
    """Check if OpenTelemetry is enabled via environment variable.

    Accepts 'true', '1', or 'yes' (case-insensitive).
    """
    return os.environ.get("OTEL_ENABLED", "false").lower() in ("true", "1", "yes")


def setup_telemetry(app: FastAPI) -> bool:
    """Initialize OpenTelemetry instrumentation for the FastAPI application.

    When OTEL_ENABLED is not set to true/1/yes, this function returns immediately
    with zero overhead. When enabled, it initializes the TracerProvider, instruments
    FastAPI, SQLAlchemy, and httpx, and exports spans via OTLP gRPC.

    If the configured collector is unreachable, the application continues serving
    normally — a warning is logged but no exception is raised.

    Args:
        app: The FastAPI application instance.

    Returns:
        True if instrumentation was successfully initialized, False otherwise.
    """
    global _OTEL_INITIALIZED

    if _OTEL_INITIALIZED:
        return True

    if not _is_otel_enabled():
        logger.debug("OpenTelemetry disabled (OTEL_ENABLED != true/1/yes)")
        return False

    service_name = os.environ.get("OTEL_SERVICE_NAME", "ai-for-trader-api")
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    # Create resource with service metadata
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "2.0.0",
            "deployment.environment": "production" if not app.debug else "development",
        }
    )

    # Configure tracer provider with OTLP gRPC exporter
    try:
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception:
        logger.warning(
            "OpenTelemetry: failed to initialize TracerProvider (collector at %s may be "
            "unreachable). Application will continue serving without tracing.",
            otlp_endpoint,
            exc_info=True,
        )
        return False

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,docs,redoc,openapi.json",
    )

    # Instrument SQLAlchemy (if engine is available)
    try:
        from app.db.database import _get_engine

        engine = _get_engine()
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        logger.info("OpenTelemetry: SQLAlchemy instrumentation enabled")
    except Exception:
        logger.debug("OpenTelemetry: SQLAlchemy instrumentation skipped", exc_info=True)

    # Instrument httpx (outbound HTTP calls)
    try:
        HTTPXClientInstrumentor().instrument()
        logger.info("OpenTelemetry: HTTPX instrumentation enabled")
    except Exception:
        logger.debug("OpenTelemetry: HTTPX instrumentation skipped", exc_info=True)

    _OTEL_INITIALIZED = True
    logger.info(
        "OpenTelemetry initialized: service=%s, endpoint=%s",
        service_name,
        otlp_endpoint,
    )
    return True
