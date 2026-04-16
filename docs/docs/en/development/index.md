# Development

This section covers development guidelines for Backtrader Web.

## Project Structure

```
backtrader_web/
├── src/
│   ├── backend/              # FastAPI Backend
│   │   ├── app/
│   │   │   ├── api/        # API Routes (15+ modules)
│   │   │   ├── services/   # Business Logic
│   │   │   ├── db/         # Database Layer
│   │   │   ├── models/     # ORM Models
│   │   │   └── schemas/    # Pydantic Models
│   │   └── strategies/     # Built-in Strategies
│   └── frontend/           # Vue3 Frontend
│       ├── src/
│       │   ├── api/        # API Calls
│       │   ├── components/ # Components
│       │   ├── views/      # Pages
│       │   └── stores/     # Pinia State
│       └── package.json
├── strategies/             # 118 Built-in Strategy Templates
├── tests/                 # Tests
└── docs/                  # Documentation
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| Backend | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| Database | SQLite (default) / PostgreSQL / MySQL |
| Testing | pytest + Playwright + Vitest |

## Guides

- [Architecture](./architecture.md) - System architecture
- [API Reference](./api.md) - RESTful API documentation
- [Database](./database.md) - Database design and models
