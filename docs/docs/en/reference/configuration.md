# Configuration

Configuration comes from `src/backend/.env` locally or deployment environment variables. Example values show shape only; never commit real secrets or passwords.

## Core and security

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Encryption and JWT signing; production must use distinct, high-entropy values. |
| `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES` | JWT algorithm and expiry. |
| `HOST`, `PORT`, `CORS_ORIGINS` | Listener and allowed origins; explicitly use `HOST=0.0.0.0` in containers. |
| `ADMIN_*` | Initial-admin bootstrap; replace defaults and restrict use in production. |

## Database and data

| Variable | Purpose |
| --- | --- |
| `DATABASE_TYPE`, `DATABASE_URL` | Application database (SQLite/PostgreSQL/MySQL). |
| `AKSHARE_DATA_DATABASE_URL` | Separate AkShare/MySQL market-data warehouse. |
| `AKSHARE_SCHEDULER_*`, `AKSHARE_SCRIPT_ROOT` | Data-script and scheduler configuration. |
| `SYNC_LOCAL_MYSQL_*` | Local MySQL connection for data synchronization; configure only when syncing. |
| `DB_AUTO_CREATE_SCHEMA`, `DB_AUTO_CREATE_DEFAULT_ADMIN` | Development bootstrap flags; usually off in production. |

## AI and RAG

| Variable | Purpose |
| --- | --- |
| `AI_CHAT_ENABLED`, `AI_CHAT_BASE_URL`, `AI_CHAT_API_KEY`, `AI_CHAT_MODEL` | OpenAI-compatible generation provider. |
| `AI_CHAT_TIMEOUT`, `AI_CHAT_TEMPERATURE`, `AI_CHAT_MAX_TOKENS` | Invocation limits and sampling settings. |
| `RAG_VECTOR_ENABLED` | Enables local semantic-vector retrieval. |
| `RAG_EMBEDDING_MODEL`, `RAG_VECTOR_COLLECTION`, `RAG_VECTOR_UPSERT_BATCH_SIZE` | Embedding model, collection, and batching. |

Without a configured model, the knowledge base can still provide index and lexical-retrieval diagnostics; do not present an empty API key as an available provider. Install the `rag` extra before enabling vector retrieval.

## Minimal example

```bash
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///../../data/dev/backtrader.db
SECRET_KEY=replace-me
JWT_SECRET_KEY=replace-me-with-another-random-value
AI_CHAT_ENABLED=false
RAG_VECTOR_ENABLED=true
```

See [Production](../deployment/production.md) for deployment configuration, backup, and access controls.
