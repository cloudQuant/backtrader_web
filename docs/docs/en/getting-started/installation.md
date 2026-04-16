# Installation Guide

## Environment Requirements

- **Python**: 3.10+
- **Node.js**: 20+
- **Docker**: 24+ (optional, for containerized deployment)
- **Git**

## Backend Installation

### 1. Create Virtual Environment

```bash
cd src/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -e ".[dev,backtrader]"
```

This installs:
- Core dependencies (FastAPI, SQLAlchemy, etc.)
- Development dependencies (pytest, ruff)
- Backtrader and related packages

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Database (default SQLite)
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite:///./backtrader.db

# Optional: PostgreSQL
# DATABASE_TYPE=postgresql
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/backtrader

# Optional: MySQL
# DATABASE_TYPE=mysql
# DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/backtrader

# JWT Configuration
SECRET_KEY=your-secret-key-here
JWT_EXPIRE_MINUTES=1440
```

### 4. Verify Installation

```bash
# Check environment
cd ../..
./scripts/verify-dev-env.sh --postinstall
```

## Frontend Installation

### 1. Install Node Dependencies

```bash
cd src/frontend
npm install
```

### 2. Configuration

Create `.env` file in `src/frontend/` if needed:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## Start Services

### Development Mode

**Terminal 1 - Backend:**
```bash
cd src/backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd src/frontend
npm run dev
```

### Docker Deployment

```bash
# Production environment
docker compose -f docker-compose.prod.yml up -d
```

## Access Addresses

| Service | Address |
|---------|---------|
| Frontend (Dev) | http://localhost:8080 |
| Frontend (Docker) | http://localhost |
| Backend API Docs | http://localhost:8000/docs |
| WebSocket | ws://localhost:8000/ws |

## Troubleshooting

### Backtrader Import Issues

If you encounter backtrader import errors, see [Backtrader Import Troubleshooting](../../BACKTRADER_IMPORT_TROUBLESHOOTING.md).

### Database Connection Issues

Ensure your database service is running and credentials are correct in `.env`.

### Port Conflicts

If ports 8000 or 8080 are in use, modify the port in the startup command:

```bash
uvicorn app.main:app --reload --port 8001
```
