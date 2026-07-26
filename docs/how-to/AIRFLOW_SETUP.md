# Airflow 本地开发环境搭建

## 方式一：本地 pip 安装（推荐开发调试）

```bash
# 1. 安装 Airflow（约 2 分钟）
pip install "apache-airflow==2.8.1" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt"

# 2. 设置 Airflow Home（DAG 文件目录）
export AIRFLOW_HOME=$(pwd)/airflow_home
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags
export AIRFLOW__CORE__DEFAULT_TIMEZONE=Asia/Shanghai
export AIRFLOW__CORE__LOAD_EXAMPLES=false
export AIRFLOW__API__AUTH_BACKENDS=airflow.api.auth.backend.basic_auth

# 3. 初始化数据库（SQLite，本地开发用）
airflow db init

# 4. 创建管理员用户
airflow users create \
  --username admin \
  --password admin \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@localhost

# 5. 启动 Webserver（后台运行）
airflow webserver --port 8080 -D

# 6. 启动 Scheduler（后台运行）
airflow scheduler -D

# 7. 验证
curl http://localhost:8080/api/v1/health
# 应返回: {"metadatabase":{"status":"healthy"},"scheduler":{"status":"healthy"}}
```

## 方式二：Docker Compose（推荐生产部署）

```bash
docker compose -f docker-compose.yml -f docker/compose/airflow.yml up -d
# 等待约 60 秒后访问 http://localhost:8080
# 用户名: admin  密码: admin
```

## 配置 AI for Investor 连接 Airflow

在 `.env` 文件中添加：

```env
# Airflow 集成
AIRFLOW_API_BASE_URL=http://localhost:8080/api/v1
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin
ORCHESTRATION_BACKEND=auto
AIRFLOW_DAG_OUTPUT_DIR=./dags
AIRFLOW_CALLBACK_BASE_URL=http://localhost:8000
```

## 验证集成

```bash
# 启动 AI for Investor 后端
cd src/backend && python -m uvicorn app.main:app --reload

# 检查编排状态
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/data/airflow/orchestration/status
# 应返回: {"type": "airflow", "connected": true, ...}
```

## 停止 Airflow

```bash
# 本地安装方式
cat $AIRFLOW_HOME/airflow-webserver.pid | xargs kill
cat $AIRFLOW_HOME/airflow-scheduler.pid | xargs kill

# Docker 方式
docker compose -f docker-compose.yml -f docker/compose/airflow.yml down
```
