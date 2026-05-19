# CI/CD Pipeline Documentation

## Overview

The Backtrader Web project uses GitHub Actions for continuous integration and continuous deployment. The CI/CD pipeline ensures code quality, runs automated tests, and validates pull requests before merging.

## Workflows

### 1. CI - Quality Checks (`.github/workflows/ci.yml`)

**Triggers:**
- Push to `master` or `develop` branches
- Pull requests to `master` or `develop`
- Manual workflow dispatch

**Jobs:**

#### Backend Jobs
| Job | Description |
|-----|-------------|
| `backend-lint` | Runs Ruff linter and import sorting checks |
| `backend-test` | Runs pytest with coverage reporting |
| `backend-security` | Runs Bandit security linter and Safety vulnerability scanner |

#### Frontend Jobs
| Job | Description |
|-----|-------------|
| `frontend-lint` | Runs ESLint and TypeScript type checks |
| `frontend-test` | Runs Vitest unit tests with coverage |
| `frontend-build` | Validates production build |

#### Integration
| Job | Description |
|-----|-------------|
| `integration-test` | Runs integration tests with PostgreSQL service |
| `ci-summary` | Aggregates all job results |

### 2. E2E - End-to-End Tests (`.github/workflows/e2e.yml`)

**Triggers:**
- Push to `master` or `develop` branches
- Pull requests to `master` or `develop`
- Manual workflow dispatch (with browser selection)

**Jobs:**

| Job | Browser | Description |
|-----|---------|-------------|
| `e2e-chromium` | Chrome | Runs full E2E test suite on Chromium |
| `e2e-firefox` | Firefox | Runs full E2E test suite on Firefox |
| `e2e-webkit` | Safari | Runs full E2E test suite on WebKit (Safari engine) |
| `e2e-mobile` | Mobile | Runs E2E tests on mobile viewport configurations |
| `e2e-summary` | - | Generates summary report of all browser tests |

**Artifacts:**
- Playwright HTML reports (14 days retention)
- Screenshots on failure (14 days retention)
- Trace files on failure (14 days retention)

### 3. PR - Pull Request Checks (`.github/workflows/pr-check.yml`)

**Triggers:**
- Pull request opened, synchronized, or reopened
- Pull request labeled

**Jobs:**

| Job | Description |
|-----|-------------|
| `pr-validation` | Validates PR description and linked issues |
| `size-check` | Checks PR size and number of changed files |
| `review-checklist` | Posts automated review checklist |
| `smoke-tests` | Runs quick smoke tests (imports, build) |
| `label-check` | Validates required PR labels |
| `merge-ready` | Adds/removes `merge-ready` label based on results |

**Labels:**
- Type labels: `feature`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`
- Status labels: `merge-ready`

### 4. Nightly - Comprehensive Tests (`.github/workflows/nightly.yml`)

**Triggers:**
- Scheduled: 2 AM UTC (10 AM Beijing) daily
- Manual workflow dispatch

**Jobs:**

| Job | Description |
|-----|-------------|
| `backend-full-tests` | Full backend test suite with detailed coverage |
| `frontend-full-tests` | Full frontend test suite with coverage |
| `e2e-full-tests` | E2E tests on all browsers |
| `performance-tests` | API performance benchmarks |
| `dependency-audit` | Security audit for dependencies |
| `nightly-summary` | Aggregates nightly test results |

**Artifacts:**
- Coverage reports (30 days retention)
- Audit reports (30 days retention)
- E2E test reports (30 days retention)

## Usage

### Running Workflows Locally

#### Backend Tests

```bash
cd src/backend

# Install dependencies
pip install -e ".[dev,backtrader]"

# Run linting
ruff check .

# Run tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=html --cov-report=term
```

#### Frontend Tests

```bash
cd src/frontend

# Install dependencies
npm install

# Run linting
npm run lint

# Run unit tests
npm run test

# Run E2E tests
npm run test:e2e

# Run E2E tests with UI
npm run test:e2e:ui

# Run E2E tests in debug mode
npm run test:e2e:debug
```

### CI Status Badges

Add these badges to your README:

```markdown
![CI Status](https://github.com/username/backtrader_web/workflows/CI%20-%20Quality%20Checks/badge.svg)
![E2E Tests](https://github.com/username/backtrader_web/workflows/E2E%20-%20End-to-End%20Tests/badge.svg)
```

### Coverage Reports

Coverage reports are uploaded to Codecov for visualization and trend analysis.

To set up Codecov:
1. Sign up at https://codecov.io
2. Link your repository
3. Add `CODECOV_TOKEN` secret to GitHub Actions settings

## Configuration

### Environment Variables

Create these secrets in your GitHub repository settings (Settings > Secrets and variables > Actions):

| Variable | Description | Required |
|----------|-------------|----------|
| `CODECOV_TOKEN` | Codecov authentication token | Optional |
| `NPM_TOKEN` | npm token for private packages | Optional |

### Workflow Dispatch Parameters

The E2E workflow supports manual triggering with browser selection:

```bash
# Via GitHub UI: Actions > E2E - End-to-End Tests > Run workflow
# Select browser: all, chromium, firefox, webkit
```

### Customization

#### Change Python Version

Edit `PYTHON_VERSION` in workflow files:

```yaml
env:
  PYTHON_VERSION: "3.11"  # Change from "3.10"
```

#### Change Node.js Version

Edit `NODE_VERSION` in workflow files:

```yaml
env:
  NODE_VERSION: "22"  # Change from "20"
```

#### Modify Test Timeout

Adjust timeout in `playwright.config.ts`:

```typescript
export default defineConfig({
  timeout: 60 * 1000,  // 60 seconds
  // ...
});
```

## Troubleshooting

### Common Issues

#### 1. Flaky E2E Tests

**Symptoms:** Tests pass locally but fail in CI

**Solutions:**
- Increase timeout in `playwright.config.ts`
- Use `waitForSelector` instead of fixed waits
- Check for race conditions in test data setup

#### 2. Backend Import Errors

**Symptoms:** `ImportError` or `ModuleNotFoundError`

**Solutions:**
```bash
# Reinstall dependencies
pip install -e ".[dev,backtrader]"

# Check PYTHONPATH in CI
env:
  PYTHONPATH: src/backend
```

#### 3. Frontend Build Failures

**Symptoms:** Build fails in CI but succeeds locally

**Solutions:**
- Check Node.js version consistency
- Clear npm cache: `npm cache clean --force`
- Verify all dependencies are in `package.json`

#### 4. Database Connection Issues

**Symptoms:** Integration tests fail with database errors

**Solutions:**
- Verify service health check configuration
- Increase startup wait time
- Check database credentials in test configuration

### Debug Mode

#### Debug GitHub Actions

1. Go to Actions > Select workflow run
2. Click on the failed job
3. Expand the logs for detailed error messages
4. Use `tmate` action for interactive debugging:

```yaml
- name: Setup tmate session
  if: failure()
  uses: mxschmitt/action-tmate@v3
```

#### Debug E2E Tests Locally

```bash
# Run with debug mode - opens inspector
npm run test:e2e:debug

# Run headed mode - see browser
npm run test:e2e:headed

# Run specific test file
npx playwright test auth.spec.ts --project=chromium
```

### Performance Optimization

#### Speed Up CI Runs

1. **Use Caching**: Workflows already cache pip and npm dependencies
2. **Parallel Jobs**: Backend and frontend jobs run in parallel
3. **Conditional Tests**: Skip slow tests on PRs, run on merge only

#### Reduce Resource Usage

```yaml
# Limit concurrency
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## Best Practices

### Writing CI-Friendly Tests

1. **Isolation**: Each test should be independent
2. **Deterministic**: Avoid random data, use seeded fixtures
3. **Fast**: Unit tests should run in milliseconds
4. **Clear failures**: Use descriptive assertions

### Pull Request Guidelines

1. **Small PRs**: Keep changes under 500 lines
2. **Descriptive**: Explain what and why, not just how
3. **Linked issues**: Reference related issues with `#123`
4. **Labels**: Add appropriate type labels

### Commit Message Format

Follow conventional commits:

```
<type>: <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

Example:
```
feat: add E2E test for user authentication flow

- Add login page tests
- Add password reset flow tests
- Add session persistence tests

Closes #123
```

## Monitoring

### Status Page

View all workflow runs at:
```
https://github.com/username/backtrader_web/actions
```

### Notifications

Configure notifications in:
Settings > Notifications > Actions

### Metrics

Key metrics to monitor:
- Average workflow duration
- Test pass rate
- Flaky test rate
- Coverage trend

## Extensions

### Adding New Jobs

To add a new job to existing workflows:

```yaml
new-job:
  name: New Job Name
  runs-on: ubuntu-latest
  steps:
    - name: Checkout code
      uses: actions/checkout@v4
    # Add your steps
```

### Creating New Workflows

1. Create `.github/workflows/your-workflow.yml`
2. Define triggers, jobs, steps
3. Commit and push to trigger the workflow

### Third-Party Integrations

- **Codecov**: Code coverage tracking
- **Dependabot**: Automated dependency updates
- **SonarCloud**: Code quality analysis
- **CodeQL**: Security vulnerability scanning

## Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Playwright Documentation](https://playwright.dev)
- [Pytest Documentation](https://docs.pytest.org)
- [Vitest Documentation](https://vitest.dev)
