# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Database performance indexes for backtest_tasks, optimization_tasks, paper_trading_orders
- API performance monitoring middleware with X-Process-Time header
- Slow request logging (>500ms threshold)

### Changed

- Optimized slow request threshold from 5s to 500ms
- Updated frontend dependencies: axios, dayjs, dompurify, autoprefixer

## [1.0.0] - 2026-03-26

### Added

#### Core Features

- **Backtest Engine**: Full Backtrader integration with async execution
- **Strategy Management**: Create, edit, delete, version control for strategies
- **Parameter Optimization**: Grid search and Bayesian optimization support
- **Paper Trading**: Simulated trading with real-time data
- **Live Trading**: MT5/CTP exchange integration with gateway management
- **Analytics Dashboard**: Performance metrics, equity curves, drawdown analysis
- **Real-time Monitoring**: WebSocket-based live updates

#### Backend Architecture

- FastAPI async REST API with JWT authentication
- SQLAlchemy 2.0 async ORM with repository pattern
- RBAC permission system (admin/user roles)
- Strategy sandbox execution for security
- Alembic database migrations
- Multi-database support (SQLite/PostgreSQL/MySQL)

#### Frontend Features

- Vue 3 + TypeScript + Vite SPA
- Element Plus UI components
- ECharts visualization (K-lines, equity curves, metrics)
- Monaco Editor for strategy code editing
- Pinia state management
- i18n internationalization (Chinese/English)

#### Testing & Quality

- 1785+ backend unit tests with 86%+ coverage
- Playwright E2E tests (5 browser targets)
- Ruff linting (line-length=100)
- TypeScript strict mode
- Pre-commit hooks

#### CI/CD Pipeline

- GitHub Actions CI with lint, test, security scan
- Nightly test runs with coverage badges
- PR automation with review checklists
- Preview deployments

### Security

- JWT token-based authentication
- Password hashing with bcrypt
- Strategy code sandboxing
- Input validation with Pydantic
- CORS configuration
- Rate limiting support

### Documentation

- API documentation (OpenAPI/Swagger)
- Architecture design document
- Development guide
- Strategy development guide
- Project context for AI agents

---

## Version History Summary

| Version | Date | Key Changes |
|---------|------|-------------|
| 1.0.0 | 2026-03-26 | Initial stable release |
| 0.9.0 | 2026-03-20 | Live trading integration |
| 0.8.0 | 2026-03-15 | Paper trading system |
| 0.7.0 | 2026-03-10 | Parameter optimization |
| 0.6.0 | 2026-03-05 | Analytics dashboard |
| 0.5.0 | 2026-02-28 | Strategy management |
| 0.4.0 | 2026-02-20 | Backtest engine |
| 0.3.0 | 2026-02-15 | Authentication system |
| 0.2.0 | 2026-02-10 | Database layer |
| 0.1.0 | 2026-02-01 | Project scaffolding |

---

For detailed commit history, see [GitHub Releases](https://github.com/user/backtrader_web/releases).
