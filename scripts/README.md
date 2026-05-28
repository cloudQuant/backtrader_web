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

# Run E2E tests
./scripts/dev/run-e2e.sh
```
