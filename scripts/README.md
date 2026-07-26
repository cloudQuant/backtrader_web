# Scripts

Project scripts organised by purpose.

| Directory | Purpose | Examples |
|---|---|---|
| `ci/` | CI/CD pipeline checks and gates | `check_alembic_heads.py`, `bandit_gate.sh`, `export_openapi.py` |
| `ops/` | Operations, deployment, app lifecycle | `app.sh`, `deploy_server.sh`, `certbot-init.sh`, `generate_lockfiles.sh` |
| `dev/` | Local development helpers | `verify-dev-env.sh`, `seed_dev_data.py`, `run-e2e.sh` |
| `diagnostics/` | Gateway / broker connectivity probes | `smoke_ctp_gateway.py`, `test_ctp_*.py`, `diagnose_project.py` |
| `migrate/` | One-shot data migration scripts | `migrate_sqlite_to_mysql.py`, `migrate_akshare_web_to_mysql.py` |
| `windows/` | Windows-specific batch wrappers | `start_app.bat`, `stop_app.bat` |

## Quick reference

```bash
# Start the app (backend + frontend)
./scripts/ops/app.sh start

# Run all CI checks locally
./scripts/ci/check_alembic_heads.py
./scripts/ci/check_doc_links.py
./scripts/ci/bandit_gate.sh app

# Verify dev environment
./scripts/dev/verify-dev-env.sh --postinstall

# Seed and verify investor roadshow demo data
python scripts/dev/seed_roadshow_demo.py
python scripts/dev/verify_roadshow_demo.py

# Verify native stock-analysis AI assistant flow
python scripts/dev/verify_stock_analysis_ai_assistant.py

# Crawl public yunjinqi.top articles into an AI Chat knowledge base (manifest first)
python scripts/migrate/crawl_yunjinqi_to_knowledge_base.py --skip-import

# Resume the manifest and create/index documents for AI Chat
AI_FOR_INVESTOR_TOKEN='...' python scripts/migrate/crawl_yunjinqi_to_knowledge_base.py --import-only

# Run E2E tests
./scripts/dev/run-e2e.sh
```
