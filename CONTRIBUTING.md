# Contributing to AI for Investor

Thank you for your interest in contributing to AI for Investor! This document provides guidelines and instructions for contributors.

## Table of Contents

- [Development Workflow](#development-workflow)
- [Setting Up Development Environment](#setting-up-development-environment)
- [Dependency Management](#dependency-management)
- [Running Tests](#running-tests)
- [Coding Standards](#coding-standards)
- [Submitting Changes](#submitting-changes)
- [Code Review Process](#code-review-process)

## Development Workflow

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
git clone https://github.com/YOUR_USERNAME/backtrader_web.git
cd backtrader_web
```

### 2. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bug-fix
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `refactor/` - Code refactoring
- `docs/` - Documentation changes
- `test/` - Test additions or updates

### 3. Make Your Changes

Follow the coding standards outlined below.

### 4. Run Tests Locally

Ensure all tests pass before pushing (see [Running Tests](#running-tests)).

### 5. Commit Your Changes

Use conventional commit messages:

```bash
git commit -m "feat: add new strategy backtest feature"
```

提交前自检清单：

- 不要提交数据库文件（如 `backtrader.db`）或其他本地产生的数据副本
- 不要提交 coverage 产物（如 `coverage.xml`、`coverage.json`、`htmlcov/`、`.coverage.*`）
- 不要提交真实 `.env`、API Key、JWT 密钥、管理员密码或其他敏感配置
- 不要提交 IDE / 系统元数据（如 `.DS_Store`、`.idea/`、临时日志、调试输出）
- 提交前确认 `git status` 中没有意外的生成文件或大体积产物

Commit types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes

### 6. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Setting Up Development Environment

### Prerequisites

- Python 3.10+
- Node.js 20+
- PostgreSQL 14+ (optional, for integration tests)
- Redis 7+ (optional)

### Backend Setup

```bash
cd src/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev,postgres,redis,backtrader]"

# Run database migrations
python -c "from app.db.database import init_db; import asyncio; asyncio.run(init_db())"
```

### Frontend Setup

```bash
cd src/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## Dependency Management

Backend dependency declarations live in `src/backend/pyproject.toml`. Edit that file when adding,
removing, or changing backend runtime, optional, or development dependencies.

Root `config/requirements-dev.lock` and `config/requirements-prod.lock` are generated artifacts for reproducible
installs:

- `requirements-dev.lock` pins the full development toolchain plus optional dependency groups used
  by local verification.
- `requirements-prod.lock` pins the production dependency set used for deployment images and
  release checks.

Do not hand-edit lock files. Regenerate them after changing `src/backend/pyproject.toml`:

```bash
./scripts/ops/generate_lockfiles.sh
```

Commit the updated `pyproject.toml` and root lock files together. As of iteration 193
(P0-1 anti-drift fix), `config/` is the **only** location for these lockfiles--the former
`src/backend/requirements-prod.lock` / `requirements-dev.lock` copies were deleted because
they had drifted from the CI-audited set, leaving the image's shipped dependencies
unaudited. `scripts/ci/check_prod_lock_singleton.py` runs in CI to prevent a second
`requirements-prod.lock` from re-appearing; the Dockerfile `COPY`s
`config/requirements-prod.lock` directly so the install target equals the audit target.

### When to use the uv workspace (175 §9)

Iteration 175 introduced an opt-in `[tool.uv.workspace]` declaration at the repo root so the
two Python member packages (`src/backend`, `src/bt_api_py`) can be installed and validated
through a single command. Use the workspace flow when:

- you are working in **both** `src/backend` and `src/bt_api_py` in one branch and want a single
  venv resolution to keep their dependencies in lock-step;
- you want to run `make check-all` (lint + typecheck + tests across all members) before opening
  a PR.

Use the legacy single-package flow (`pip install -e ".[dev]"` inside `src/backend/`) when:

- you are only changing one member;
- you need to mirror the production install path used by deployment images.

#### Adding a third member

1. Append the new directory to `[tool.uv.workspace] members` in the root `pyproject.toml`.
2. Ensure that directory has its own `pyproject.toml`.
3. Re-run `uv sync --workspace` to refresh `uv.lock`.
4. Run `make workspace-lock-check` (= `python scripts/dev/check_workspace_lock_conflict.py`)
   to verify the new dependencies do not conflict with `config/requirements-dev.lock`.

#### Lock files & workspace coexistence

`config/requirements-dev.lock` remains the **single source of truth (SSOT)** for backend dev
installs. `uv.lock` is generated by `uv sync --workspace` for convenience and must remain
consistent with the SSOT — `make workspace-lock-check` runs in CI's `monorepo-check`
(advisory) job to catch drift early.

## Running Tests

### Backend Tests

```bash
cd src/backend

# Run all tests
pytest

# Run specific test file
pytest tests/test_auth.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run integration tests
pytest -m integration

# Run with verbose output
pytest -v
```

### Frontend Unit Tests

```bash
cd src/frontend

# Run all unit tests
npm run test

# Run with coverage
npm run test -- --coverage

# Watch mode
npm run test -- --watch
```

### E2E Tests

```bash
# Using the E2E runner script (recommended)
./scripts/dev/run-e2e.sh

# Or manually
cd src/frontend
npm run test:e2e

# With UI mode
npm run test:e2e:ui

# Debug mode
npm run test:e2e:debug

# Specific browser
npx playwright test --project=chromium

# Specific test file
npx playwright test auth.spec.ts
```

### Using Docker for E2E Tests

```bash
# Start all services
docker compose -f docker/docker-compose.yml -f docker/compose/ci.yml up -d

# Run E2E tests
cd src/frontend
export BASE_URL=http://localhost:3000
npm run test:e2e

# Stop services
docker compose -f docker/docker-compose.yml -f docker/compose/ci.yml down
```

## Coding Standards

### Python (Backend)

- Follow PEP 8 style guidelines
- Use Ruff for linting and formatting
- Maximum line length: 100 characters
- Use type hints for function signatures
- Write docstrings for public functions and classes

```python
from typing import List, Optional

def get_strategies(user_id: int, active: Optional[bool] = None) -> List[dict]:
    """
    Retrieve strategies for a user.

    Args:
        user_id: The user's ID
        active: Filter by active status

    Returns:
        List of strategy dictionaries
    """
    # Implementation...
```

### TypeScript/Frontend

- Use ESLint for linting
- Follow Vue 3 Composition API patterns
- Use Pinia for state management
- Write meaningful component names

```typescript
// Good
<script setup lang="ts">
import { ref, computed } from 'vue'

interface Strategy {
  id: number
  name: string
}

const strategies = ref<Strategy[]>([])
const activeCount = computed(() => strategies.value.filter(s => s.active).length)
</script>
```

### Testing Guidelines

- Unit tests should be fast and isolated
- E2E tests should cover critical user flows
- Mock external dependencies (API calls, database)
- Use descriptive test names

```python
# Good test name
def test_login_with_valid_credentials_returns_token():
    # ...
```

## Submitting Changes

### Pull Request Checklist

Before submitting a PR, ensure:

- [ ] All tests pass locally
- [ ] Code follows style guidelines
- [ ] New features include tests
- [ ] Documentation is updated
- [ ] Commit messages follow conventions
- [ ] PR description is clear and complete

### Pull Request Description Template

```markdown
## Summary
Brief description of changes.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe testing performed.

## Screenshots (if applicable)
Add screenshots for UI changes.

## Related Issues
Fixes #123
Related to #456
```

## Code Review Process

### Review Guidelines

1. **Be Constructive**: Provide helpful feedback
2. **Be Respectful**: Treat others with respect
3. **Be Timely**: Respond to reviews promptly
4. **Explain Why**: Explain reasoning for suggestions

### Reviewer Checklist

- [ ] Code follows project standards
- [ ] Tests are adequate
- [ ] No security vulnerabilities
- [ ] Performance impact considered
- [ ] Documentation updated

### Addressing Review Comments

1. Make requested changes
2. Reply to each comment with your response
3. Mark conversations as resolved when addressed
4. Request re-review when ready

## CI/CD Pipeline

All pull requests go through automated checks:

1. **Lint**: Code style checks
2. **Tests**: Unit and integration tests
3. **Build**: Production build validation
4. **E2E**: End-to-end browser tests
5. **Security**: Security vulnerability scanning

See [CI/CD Documentation](docs/operations/CI_CD.md) for details.

## Sharing a Repro Bundle (Scrub Secrets First)

When you attach logs, a zipped project copy, screenshots, or a support bundle to
an issue or chat, **scrub local credentials before sharing**. Developer-local
`.env` files and `strategies/simulate/*/.env` may hold real third-party keys
(OKX / Binance / HTX / CTP / Telegram / PyPI / ReadTheDocs). These are never
committed (they are `.gitignore`d), but they can leak through bundles.

Checklist before sharing any bundle:

- [ ] Remove or redact every `.env` / `*.env` file from the bundle
      (`find . -name '*.env' -print` to locate them).
- [ ] Strip credentials from logs: API keys, JWT secrets, admin passwords,
      broker tokens, session cookies.
- [ ] Redact secrets visible in screenshots (URLs with tokens, header panes).
- [ ] If a key was ever exposed (screenshot, CI artifact, shared bundle),
      **rotate it** at the provider and update your local `.env`.
- [ ] Prefer `.env.example` (placeholder values only) when showing config shape.

If you discover a credential leaked through a past bundle, treat it as an
incident: rotate the affected keys first, then audit where the bundle traveled.

## Getting Help

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Check existing documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
