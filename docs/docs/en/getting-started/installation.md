# Installation

## Requirements

- Python 3.10+
- Node.js 20+
- Git
- Docker Compose v2 (optional, for containerized environments)

## Local development

```bash
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

./scripts/dev/verify-dev-env.sh --preinstall

# Backend
cd src/backend
python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -e ".[dev,backtrader]"
# For online AkShare refreshes: pip install -e ".[dev,backtrader,data]"
# For semantic retrieval: pip install -e ".[dev,backtrader,rag]"
cp .env.example .env

# Frontend
cd ../frontend
npm install

cd ../..
./scripts/dev/verify-dev-env.sh --postinstall
```

Keep environment-specific configuration in `.env`, replace secret placeholders, and never commit the file. A minimal configuration is:

```bash
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///../../data/dev/backtrader.db
SECRET_KEY=replace-with-a-random-secret
JWT_SECRET_KEY=replace-with-a-different-random-secret
```

For a MySQL application database, set `DATABASE_TYPE=mysql` and `DATABASE_URL=mysql+aiomysql://...`. The market-data warehouse has a separate `AKSHARE_DATA_DATABASE_URL`; see [Market data](../features/market-data.md).

## Start services

Run these in separate terminals:

```bash
# Backend
cd src/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend
cd src/frontend
npm run dev
```

The development frontend is `http://localhost:3000`; API documentation is at `http://localhost:8000/docs`.

## Docker

The Compose base file lives at `docker/docker-compose.yml`. Choose an environment override:

```bash
docker compose -f docker/docker-compose.yml -f docker/compose/dev.yml up
# Or the production override
docker compose -f docker/docker-compose.yml -f docker/compose/prod.yml up -d
```

Continue with [Docker deployment](../deployment/docker.md), and configure database, secrets, CORS, and backups before starting production.
