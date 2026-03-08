# Installation Guide

This guide covers the supported local development setup for Backtrader Web.

## Prerequisites

- Operating system: Linux, macOS, or Windows with WSL2 recommended
- Python: 3.10 or higher
- Node.js: 20 LTS
- Git

## 1. Clone the Repository

```bash
git clone https://github.com/your-org/backtrader_web.git
cd backtrader_web
```

## 2. Run Preinstall Checks

Use the preinstall verifier before creating environments or installing project dependencies.

```bash
./scripts/verify-dev-env.sh --preinstall
```

If this fails, fix the reported Node or Python mismatch first.

## 3. Set Up the Backend Environment

```bash
cd src/backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -e ".[dev,backtrader]"
cp .env.example .env
cd ../..
```

## 4. Run Postinstall Checks

After backend dependencies are installed, verify runtime imports.

```bash
./scripts/verify-dev-env.sh --postinstall
```

This checks `backtrader`, `backtrader.Analyzer`, `fastapi`, and `sqlalchemy`.

## 5. Set Up the Frontend

```bash
cd src/frontend
npm ci
cd ../..
```

## 6. Initialize the Database

Database initialization is explicit. The application no longer creates tables or
the default administrator account during startup.

```bash
cd src/backend
python scripts/init_db.py --init-all
cd ../..
```

For more detail, see [Database Initialization Guide](DATABASE_INIT.md).

## 7. Start the Application

Backend:

```bash
cd src/backend
source venv/bin/activate   # Windows: venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd src/frontend
npm run dev
```

## Access URLs

- Frontend: `http://localhost:3000`
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Quick API Smoke Test

Register:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!",
    "email": "admin@example.com"
  }'
```

Login:

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!"
  }'
```

## Troubleshooting

### Backtrader Import Fails

```bash
./scripts/verify-dev-env.sh --postinstall
```

If `Analyzer` is missing, reinstall backend dependencies:

```bash
cd src/backend
pip install -e ".[dev,backtrader]"
```

### Database Tables Do Not Exist

Initialize them explicitly:

```bash
cd src/backend
python scripts/init_db.py --create-tables
```

### Port 8000 or 3000 Is Already in Use

Start the service on a different port after updating the matching config and proxy settings.
