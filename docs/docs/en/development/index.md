# Development

Development documentation describes the repository’s current layering boundaries. Tests and OpenAPI define the released contract and runtime behavior.

## Layout and responsibilities

```text
src/backend/app/
├── api/        # HTTP/WebSocket routes, auth, and input/output boundary
├── services/   # Data, RAG, backtest, workspace, trading, and risk orchestration
├── models/     # SQLAlchemy ORM models
├── schemas/    # Pydantic request/response models
├── db/         # Engines, sessions, repositories, and migration support
└── utils/      # Security, sandbox, logging, and infrastructure helpers

src/frontend/src/
├── api/        # API clients
├── views/      # Routed pages
├── components/ # Reusable UI
├── composables/# Page and domain composition
├── stores/     # Pinia state
└── navigation/ # Route and navigation conventions
```

## Continue reading

- [Architecture](./architecture.md)
- [API reference](./api.md)
- [Database and data boundaries](./database.md)
- Engineering coding standards: `docs/reference/CODING_STANDARDS.md`
- Engineering test guide: `docs/how-to/TESTING.md`
