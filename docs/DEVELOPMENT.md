# Development Guide

## Backend

### Install

```bash
./scripts/verify-dev-env.sh --preinstall
cd src/backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,backtrader]"
cd ../..
./scripts/verify-dev-env.sh --postinstall
```

### Run

```bash
cd src/backend
uvicorn app.main:app --reload --port 8000
```

### Test

```bash
cd src/backend
python -m pytest
```

### Lint

```bash
cd src/backend
python -m ruff check .
```

### Coverage

```bash
cd src/backend
python -m coverage run -m pytest
python -m coverage report -m
python -m coverage html
```

The HTML report is generated under `src/backend/htmlcov/`.

## Frontend

```bash
cd src/frontend
npm ci
npm run dev
```
