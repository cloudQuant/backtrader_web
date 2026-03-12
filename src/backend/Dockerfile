# Dockerfile for CI/CD and Production
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖声明，利用层级缓存（依赖变更频率低）
# pyproject.toml 为单一事实来源，不依赖 requirements.txt
COPY pyproject.toml .

# 复制应用代码（pip install -e 需完整源码）
COPY . .

# 安装依赖：以 pyproject.toml 为单一来源，extras 覆盖 postgres/redis/backtrader/data(akshare)
RUN pip install --no-cache-dir -e ".[postgres,redis,backtrader,data]"

# 创建数据目录
RUN mkdir -p /app/data /app/logs

# 创建非 root 用户 (用于生产环境)
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
