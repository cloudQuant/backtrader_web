# Dockerfile for CI/CD and Production
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/workspace/backtrader_web/src/backend

# 安装系统依赖
RUN true

COPY src/backend /opt/workspace/backtrader_web/src/backend
COPY src/bt_api_py /opt/workspace/bt_api_py
COPY strategies /opt/workspace/backtrader_web/strategies
COPY data /opt/workspace/backtrader_web/data

RUN pip install --no-cache-dir -e ".[postgres,mysql,redis,backtrader,data]"

RUN mkdir -p \
    /opt/workspace/backtrader_web/datas \
    /opt/workspace/backtrader_web/workspace_units \
    /opt/workspace/backtrader_web/src/backend/data \
    /opt/workspace/backtrader_web/src/backend/logs

# 创建非 root 用户 (用于生产环境)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /opt/workspace

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:{}/health'.format(os.environ.get('PORT', '8000')))"

# 启动命令
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
