# Development Dockerfile for Backend (FastAPI + Uvicorn with hot-reload)
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies (curl for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/workspace/backtrader_web/src/backend

# Copy dependency files first for better layer caching
COPY src/backend/pyproject.toml /opt/workspace/backtrader_web/src/backend/

# Install Python dependencies in editable mode
RUN pip install -e ".[dev,backtrader]" 2>/dev/null || pip install -e ".[dev]"

# Create necessary directories
RUN mkdir -p \
    /opt/workspace/backtrader_web/datas \
    /opt/workspace/backtrader_web/workspace_units \
    /opt/workspace/backtrader_web/src/backend/data \
    /opt/workspace/backtrader_web/src/backend/logs \
    /opt/workspace/backtrader_web/strategies

# Copy entrypoint script
COPY docker/entrypoint-dev.sh /usr/local/bin/entrypoint-dev.sh
RUN chmod +x /usr/local/bin/entrypoint-dev.sh

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint-dev.sh"]
CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
