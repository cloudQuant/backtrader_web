# Common commands

Run these from the repository root. Use the project’s designated Python environment for backend commands.

## Backend

```bash
cd src/backend
pip install -e ".[dev,backtrader]"
pytest -m "not e2e" -q --tb=short
ruff check app tests
mypy app
uvicorn app.main:app --reload --port 8000
```

Install the appropriate extra for online data or semantic retrieval:

```bash
pip install -e ".[data]"
pip install -e ".[rag]"
```

## Frontend

```bash
cd src/frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm run test -- --run
npm run build
```

## Documentation

```bash
python -m pip install -r docs/requirements.txt
python -m mkdocs serve -f docs/mkdocs.yml
python -m mkdocs build -f docs/mkdocs.yml --strict
```

## Docker

```bash
# Development Compose
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up

# Production Compose
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml ps
```

Before high-impact commands, check environment, configuration, and backup state. Test/development commands must not use production databases or real gateway credentials.
