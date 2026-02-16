# Backtrader Web

A modern web backtesting platform built around Backtrader.

## Tech Stack

- Frontend: Vue 3 + TypeScript + Vite + Element Plus + ECharts
- Backend: FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0
- Database: SQLite (default), PostgreSQL/MySQL (optional)

## Quick Start

### Requirements

- Python 3.10+
- Node.js 18+

### Backend

```bash
cd src/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Open API docs: `http://localhost:8000/docs`

### Frontend

```bash
cd src/frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

## Documentation

- User guide: `docs/USER_GUIDE.md`
- Development guide: `docs/DEVELOPMENT.md`
- API guide: `docs/API.md`

## Examples

- Backend API quickstart: `examples/backend_api_quickstart.py`

