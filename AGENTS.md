# AGENTS.md - Coding Agent Instructions

Essential info for AI agents working on Backtrader Web, a quantitative trading platform.

**Tech Stack**: Python 3.10+ (FastAPI, SQLAlchemy 2.0, Pydantic) | Vue 3 + TypeScript (Vite, Element Plus, Pinia) | SQLite/PostgreSQL/MySQL

---

## Build/Test/Lint Commands

### Backend (`src/backend/`)

```bash
pip install -e ".[dev,backtrader]"     # Install dependencies
pytest                                   # Run all tests
pytest tests/test_auth.py               # Run single test file
pytest tests/test_auth.py::TestRegister::test_register_success  # Run single test
pytest --cov=app --cov-report=term      # Tests with coverage
pytest -v -s                            # Verbose output
pytest -m "not e2e"                     # Skip e2e tests
ruff check src/backend                  # Lint
ruff check src/backend --fix            # Auto-fix lint issues
ruff format src/backend                 # Format
```

### Frontend (`src/frontend/`)

```bash
npm install              # Install dependencies
npm run dev              # Development server
npm run build            # Production build
npm run test             # Unit tests
npm run test -- --coverage   # Tests with coverage
npm run test:e2e         # E2E tests (requires running app)
npm run test:e2e:headed  # E2E with visible browser
npm run lint             # Lint
```

---

## Code Style

### Python (Backend)

**Config**: `src/backend/pyproject.toml` - Line length: 100, Ruff rules: E, F, I, W

**Naming**: Files `snake_case.py`, Classes `PascalCase`, Functions `snake_case()`, Constants `UPPER_SNAKE_CASE`, API routes `kebab-case`

**Imports**: Standard lib → Third-party → Local (handled by Ruff/isort)

**Type Hints**: Required for all functions
```python
def get_strategies(user_id: int, active: Optional[bool] = None) -> List[dict]:
```

**Docstrings**: Google style for public functions/classes

**Architecture** (Layered):
- `app/api/` - Routes: request parsing, validation
- `app/services/` - Business logic (core implementation)
- `app/schemas/` - Pydantic DTOs
- `app/models/` - SQLAlchemy ORM
- `app/db/` - Repositories
- `app/middleware/` - Logging, security

**Rules**:
- One service class per file, use `@lru_cache` for singletons
- Prefer `async def` methods
- Service layer: return `None`/`False` for failures
- API layer: convert failures to `HTTPException`

**Error Handling**:
- Service: Return `None`/`False` for expected failures, raise for unexpected
- API: Convert to `HTTPException` with appropriate status codes
- Use Pydantic for input validation (automatic 422)

### TypeScript/Frontend

**Config**: `src/frontend/tsconfig.json` (strict mode)

**Naming**: Components `PascalCase.vue`, Composables/Stores `useCamelCase()`, Types `PascalCase`, Constants `UPPER_SNAKE_CASE`

**Component Structure**:
```vue
<script setup lang="ts">
// 1. Imports
import { ref, computed, onMounted } from 'vue'
// 2. Props/Emits
const props = defineProps<{ taskId: string }>()
// 3. Reactive data
const loading = ref(false)
// 4. Computed
const hasResult = computed(() => !!store.currentResult)
// 5. Methods
async function runBacktest() { /* ... */ }
// 6. Lifecycle
onMounted(() => { /* ... */ })
</script>
<style scoped>
/* Use scoped styles */
</style>
```

**Best Practices**: Use Composition API (`<script setup>`), Pinia for state, TypeScript strict mode, `async/await`

---

## Testing

**Backend** (pytest):
```python
class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={...})
        assert resp.status_code == 200
```
- Naming: `test_*.py`, `TestFeatureName`, `test_specific_scenario`
- Mock external dependencies, use fixtures in `conftest.py`
- Mark: `@pytest.mark.integration`, `@pytest.mark.e2e`

**Frontend**: Vitest + Playwright

---

## Git Commits

Conventional Commits: `<type>(<scope>): <description>`

**Types**: feat, fix, docs, style, refactor, test, chore, perf, ci

**Examples**: `feat(backtest): add cancel endpoint`, `fix(auth): handle token refresh`

---

## Security

- **Never** hardcode secrets; use `.env` (not committed)
- Validate input via Pydantic schemas
- Use parameterized queries (SQLAlchemy handles this)
- Execute strategy code in sandboxed environment

---

## Pre-commit

Config: `.pre-commit-config.yaml` (Ruff, whitespace, YAML/JSON validation)

```bash
pip install pre-commit && pre-commit install  # Setup
pre-commit run --all-files                     # Run manually
```

---

## Common Tasks

**New API Endpoint**: Schema (`app/schemas/`) → Service (`app/services/`) → Route (`app/api/`) → Tests

**New Frontend Page**: View (`src/views/`) → Route → Store (`src/stores/`) → API wrapper → Tests

**Database Change**: Model (`app/models/`) → Repository (`app/db/`) → Service → Tests

---

## Key Files

- `src/backend/pyproject.toml` - Python config
- `src/frontend/package.json` - Frontend scripts
- `docs/CODING_STANDARDS.md` - Detailed standards
- `docs/DEVELOPMENT.md` - Dev setup
