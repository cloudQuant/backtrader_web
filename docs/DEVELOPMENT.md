# Development Guide

## Backend

### Install

```bash
cd src/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
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
npm install
npm run dev
```

