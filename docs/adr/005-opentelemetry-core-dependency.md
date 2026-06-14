# ADR-005: OpenTelemetry Core Dependency

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** AI for Trader Team

## Context

OpenTelemetry (OTel) was previously an optional dependency, installed only in production
environments. This created several problems:

- Developers couldn't reproduce or debug production tracing issues locally
- Instrumentation code was wrapped in `try/except ImportError` blocks throughout the
  codebase, making it fragile and hard to maintain
- New endpoints were frequently shipped without trace instrumentation because it wasn't
  part of the default development workflow
- When production issues occurred, the first step was often "add tracing" — which
  required a new deployment

## Decision

Move OpenTelemetry packages to core (non-optional) dependencies and control activation
via environment variable:

**Core packages added to `pyproject.toml` dependencies:**
- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-instrumentation-fastapi`
- `opentelemetry-instrumentation-sqlalchemy`
- `opentelemetry-instrumentation-httpx`
- `opentelemetry-exporter-otlp-proto-grpc`

**Activation control:**
```bash
# Disabled by default — zero overhead
OTEL_ENABLED=false

# Enable with console exporter for local development
OTEL_ENABLED=true
OTEL_EXPORTER=console

# Enable with OTLP exporter for production
OTEL_ENABLED=true
OTEL_EXPORTER=otlp
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317
```

When `OTEL_ENABLED=false` (the default), the OTel SDK uses no-op implementations that
have negligible performance impact — no spans are created, no data is exported.

## Consequences

### Positive

- Tracing is always available when needed — just flip an environment variable
- No more conditional import blocks — cleaner, more maintainable code
- Developers can trace locally with `OTEL_EXPORTER=console` for debugging
- New endpoints automatically get FastAPI instrumentation without extra work
- Consistent observability across all environments (dev, staging, production)

### Negative

- Adds ~15MB to the installed package size (OTel SDK + exporters + protobuf)
- All developers install OTel packages even if they never enable tracing
- OTel SDK version updates may introduce breaking changes that affect all environments
- Slightly longer `pip install` time for fresh environments

### Neutral

- Zero runtime overhead when disabled — no-op implementations are used
- No change to application behavior or API contracts
- Compatible with any OTel-compatible backend (Jaeger, Tempo, Datadog, etc.)
- Configuration follows OTel's standard environment variable conventions
