# 配置参考

配置由 `src/backend/.env`（本地）或部署环境变量提供。示例值仅说明格式，真实密钥和密码不得提交。

## 基础与安全

| 变量 | 用途 |
| --- | --- |
| `SECRET_KEY`、`JWT_SECRET_KEY` | 加密与 JWT 签名；生产环境必须使用不同的高熵值。 |
| `JWT_ALGORITHM`、`JWT_EXPIRE_MINUTES` | JWT 算法与过期时间。 |
| `HOST`、`PORT`、`CORS_ORIGINS` | 服务监听与允许来源；容器中显式设置 `HOST=0.0.0.0`。 |
| `ADMIN_*` | 初始管理员自举；生产环境必须替换默认值并限制使用。 |

## 数据库与数据

| 变量 | 用途 |
| --- | --- |
| `DATABASE_TYPE`、`DATABASE_URL` | 应用数据库（SQLite/PostgreSQL/MySQL）。 |
| `AKSHARE_DATA_DATABASE_URL` | 独立的 AkShare/MySQL 行情数据仓。 |
| `AKSHARE_SCHEDULER_*`、`AKSHARE_SCRIPT_ROOT` | 数据脚本与调度配置。 |
| `SYNC_LOCAL_MYSQL_*` | 数据同步所用本地 MySQL 连接；仅在需要同步时配置。 |
| `DB_AUTO_CREATE_SCHEMA`、`DB_AUTO_CREATE_DEFAULT_ADMIN` | 开发自举开关；生产环境通常关闭。 |

## AI 与 RAG

| 变量 | 用途 |
| --- | --- |
| `AI_CHAT_ENABLED`、`AI_CHAT_BASE_URL`、`AI_CHAT_API_KEY`、`AI_CHAT_MODEL` | OpenAI-compatible 生成模型。 |
| `AI_CHAT_TIMEOUT`、`AI_CHAT_TEMPERATURE`、`AI_CHAT_MAX_TOKENS` | 调用边界与采样参数。 |
| `RAG_VECTOR_ENABLED` | 是否启用本地语义向量检索。 |
| `RAG_EMBEDDING_MODEL`、`RAG_VECTOR_COLLECTION`、`RAG_VECTOR_UPSERT_BATCH_SIZE` | 嵌入模型、集合和批处理设置。 |

未配置模型时，知识库仍可给出索引与词法检索诊断；不要用空 API Key 伪装为可用模型。安装 `rag` 额外依赖后才启用向量检索。

## 最小示例

```bash
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///../../data/dev/backtrader.db
SECRET_KEY=replace-me
JWT_SECRET_KEY=replace-me-with-another-random-value
AI_CHAT_ENABLED=false
RAG_VECTOR_ENABLED=true
```

部署配置、备份和访问控制见[生产环境](../deployment/production.md)。
