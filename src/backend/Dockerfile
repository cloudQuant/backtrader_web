# Dockerfile for CI/CD and Production
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/workspace/ai-for-investor/src/backend

# 安装系统依赖
RUN true

# 先 COPY 锁文件（变更频率低，利于 layer 缓存）；显式从 config/ SSOT 复制，
# 与 CI pip-audit 审计对象保持同一份文件（迭代193 P0-1：消除双锁漂移）。
COPY config/requirements-prod.lock ./requirements-prod.lock

COPY src/backend /opt/workspace/ai-for-investor/src/backend
COPY src/bt_api_py /opt/workspace/bt_api_py
COPY strategies /opt/workspace/ai-for-investor/strategies

# 按锁文件安装精确版本依赖（可复现构建）。
# 锁文件缺失应构建失败而非静默回退到 pyproject extras——回退会使镜像依赖
# 集与 CI pip-audit 审计对象再次漂移。
RUN pip install --no-cache-dir -r requirements-prod.lock && \
    pip install --no-cache-dir -e ".[prod]"

RUN mkdir -p \
    /opt/workspace/ai-for-investor/datas \
    /opt/workspace/ai-for-investor/workspace_units \
    /opt/workspace/ai-for-investor/src/backend/data \
    /opt/workspace/ai-for-investor/src/backend/logs

# 创建非 root 用户 (用于生产环境)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /opt/workspace

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:{}/health'.format(os.environ.get('PORT', '8000')))"

# 生产环境使用 Gunicorn 管理多个 Uvicorn worker
# WEB_CONCURRENCY 控制 worker 数量，默认 2（适合 2 核服务器）
# 单 worker 模式可设置 WEB_CONCURRENCY=1
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 300 --graceful-timeout 30 --access-logfile - --error-logfile -"]
