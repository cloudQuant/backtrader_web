# Development Guide

## Backend

### Install

```bash
./scripts/verify-dev-env.sh --preinstall
python -m venv src/backend/venv
source src/backend/venv/bin/activate
pip install -e "src/backend[dev,backtrader]"
cp .env.example src/backend/.env
./scripts/verify-dev-env.sh --postinstall
```

Set `DEBUG=true` in `src/backend/.env` for local development. Keep `HOST=127.0.0.1` for localhost-only work; only switch to `HOST=0.0.0.0` when you need Docker/LAN access.

### Run

```bash
source src/backend/venv/bin/activate
uvicorn app.main:app --app-dir src/backend --reload --port 8000
```

### Test

```bash
source src/backend/venv/bin/activate
pytest -n 8
```

### Lint

```bash
source src/backend/venv/bin/activate
ruff check src/backend
```

### Coverage

```bash
source src/backend/venv/bin/activate
coverage run -m pytest -n 8
coverage report -m
coverage html
```

The HTML report is generated under `src/backend/htmlcov/`.

## Frontend

```bash
npm --prefix src/frontend ci
npm --prefix src/frontend run dev
```
