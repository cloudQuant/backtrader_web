---
title: Home
description: Modern Quantitative Trading Platform based on Backtrader
---

# Backtrader Web

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Vue](https://img.shields.io/badge/Vue-3.4+-green.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Modern Quantitative Trading Full-Stack Management Platform based on Backtrader**

[Chinese](../zh/){ .md-button }
[English](../en/){ .md-button }

</div>

## Features

- 🚀 **Out-of-the-Box** - Complete first backtest in 5 minutes
- 📊 **Professional Charts** - Echarts K-line + 10+ analysis charts
- 🔌 **API-First** - 15+ modules, 80+ RESTful API endpoints
- 💾 **Multi-Database** - SQLite / PostgreSQL / MySQL
- 🎯 **Strategy Management** - Version control + code editor + 118 built-in templates
- 📈 **Paper Trading** - Complete simulated trading environment
- 🔴 **Live Trading** - Multi-broker integration (CTP/CCXT)
- 📡 **Real-time Data** - WebSocket real-time push
- 🚨 **Monitoring & Alerts** - Real-time monitoring and alerting system

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + TypeScript + Vite + Element Plus + Echarts |
| Backend | FastAPI + Uvicorn + Pydantic + SQLAlchemy 2.0 |
| Database | SQLite (default) / PostgreSQL / MySQL |
| Backtest Engine | Backtrader + fincore |
| Testing | pytest + Playwright (E2E) + Vitest |

## Quick Start

### Installation

```bash
# Clone the project
git clone https://github.com/cloudQuant/backtrader_web.git
cd backtrader_web

# Backend installation
cd src/backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,backtrader]"

# Frontend installation
cd src/frontend
npm install
```

### Start Services

**Development Mode:**
```bash
# Backend
cd src/backend && uvicorn app.main:app --reload --port 8000

# Frontend
cd src/frontend && npm run dev
```

**Docker Deployment:**
```bash
docker compose -f docker-compose.prod.yml up -d
```

### Access

- Frontend: http://localhost:8080 (dev) / http://localhost (prod Docker)
- Backend API Docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws

## Documentation

- [Getting Started](./getting-started/)
- [Installation Guide](./getting-started/installation.md)
- [Quick Start Tutorial](./getting-started/quickstart.md)
- [API Reference](./development/api.md)
- [Architecture](./development/architecture.md)

## License

[MIT License](https://github.com/cloudQuant/backtrader_web/blob/main/LICENSE)
