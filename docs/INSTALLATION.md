# Installation Guide

This guide will help you install and run the Backtrader Web quantitative trading platform on your local machine.

## Prerequisites

### System Requirements

- **Operating System**: Linux, macOS, or Windows (WSL2 recommended)
- **Python**: Version 3.8 or higher (3.11 recommended)
- **Memory**: Minimum 4GB RAM, 8GB recommended
- **Disk**: Minimum 2GB free space

### Required Software

Before installing, ensure you have the following:

- Python 3.8+ with pip
- Git (for cloning the repository)
- SQLite3 (usually included with Python)

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/backtrader_web.git
cd backtrader_web
```

### 2. Create Virtual Environment

**Linux/macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**

```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install backend dependencies
cd src/backend
pip install -r requirements.txt

# Or install using pyproject.toml (recommended)
pip install -e .
```

**Required Dependencies:**

- fastapi>=0.109.0
- uvicorn[standard]>=0.27.0
- sqlalchemy[asyncio]>=2.0.25
- aiosqlite>=0.19.0
- python-jose[cryptography]>=3.3.0
- passlib[bcrypt]>=1.7.4
- fincore>=1.0.0
- backtrader>=1.9.76
- pandas>=1.5.0
- numpy>=1.21.0

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit configuration (optional for development)
# nano .env
```

**Default Development Settings:**

```ini
DATABASE_TYPE=sqlite
DATABASE_URL=sqlite+aiosqlite:///./backtrader.db
DEBUG=true
JWT_SECRET_KEY=development-secret-key-change-in-production
JWT_EXPIRE_MINUTES=1440
```

### 5. Initialize Database

```bash
# Run database migrations (if using PostgreSQL/MySQL)
# For SQLite, the database is created automatically

python -c "from app.db.database import init_db; import asyncio; asyncio.run(init_db())"
```

### 6. Start the Backend Server

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --port 8000

# Or run directly
python -m app.main
```

The backend API will be available at:
- **API**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Quick Start

### 1. Register a User

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!",
    "email": "admin@example.com"
  }'
```

### 2. Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "SecurePassword123!"
  }'
```

Save the returned `access_token` for subsequent requests.

### 3. List Available Strategies

```bash
curl -X GET "http://localhost:8000/api/v1/strategy/templates" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### 4. Run Your First Backtest

```bash
curl -X POST "http://localhost:8000/api/v1/backtest/run" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": "ma_cross",
    "symbol": "000001.SZ",
    "start_date": "2023-01-01T00:00:00",
    "end_date": "2024-01-01T00:00:00",
    "initial_cash": 100000,
    "commission": 0.001
  }'
```

## Troubleshooting

### Python Version Issues

**Problem**: `ModuleNotFoundError: No module named '_ctypes'`

**Solution**: Ensure you're using Python 3.8+:

```bash
python --version  # Should show 3.8 or higher
```

### Import Errors

**Problem**: `ImportError: cannot import name 'fastapi'`

**Solution**: Install dependencies in the virtual environment:

```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Database Errors

**Problem**: `sqlite3.OperationalError: no such table`

**Solution**: Initialize the database:

```bash
python -c "from app.db.database import init_db; import asyncio; asyncio.run(init_db())"
```

### Port Already in Use

**Problem**: `OSError: [Errno 48] Address already in use`

**Solution**: Either stop the process using port 8000 or use a different port:

```bash
uvicorn app.main:app --reload --port 8001
```

### fincore Import Errors

**Problem**: `ImportError: cannot import name 'fincore'`

**Solution**: Install fincore:

```bash
pip install fincore>=1.0.0
```

### Permission Denied (Linux/macOS)

**Problem**: `Permission denied` when running scripts

**Solution**: Make scripts executable:

```bash
chmod +x scripts/*.sh
```

### Windows-Specific Issues

**Problem**: Event loop policy warnings

**Solution**: Set the event loop policy before importing:

```python
import asyncio
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

## Next Steps

After installation:

1. Read the [Deployment Guide](DEPLOYMENT.md) for production setup
2. Read the [Operations Guide](OPERATIONS.md) for maintenance tips
3. Check the [API Documentation](http://localhost:8000/docs) for all endpoints

## Additional Resources

- [Backend README](../src/backend/README.md)
- [Fincore Migration Guide](../src/backend/FINCORE_MIGRATION.md)
- [Project GitHub](https://github.com/your-org/backtrader_web)
