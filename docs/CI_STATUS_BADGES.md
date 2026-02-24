# CI/CD Status Badges

Add these badges to your project README to show the current status of CI/CD pipelines.

## Workflow Status Badges

### Main CI Pipeline
```markdown
![CI - Quality Checks](https://github.com/YOUR_USERNAME/backtrader_web/workflows/CI%20-%20Quality%20Checks/badge.svg)
```

### E2E Tests
```markdown
![E2E Tests](https://github.com/YOUR_USERNAME/backtrader_web/workflows/E2E%20-%20End-to-End%20Tests/badge.svg)
```

### PR Checks
```markdown
![PR Checks](https://github.com/YOUR_USERNAME/backtrader_web/workflows/PR%20-%20Pull%20Request%20Checks/badge.svg)
```

### Nightly Builds
```markdown
![Nightly Tests](https://github.com/YOUR_USERNAME/backtrader_web/workflows/Nightly%20-%20Comprehensive%20Tests/badge.svg)
```

## Coverage Badges

### Codecov
```markdown
![Codecov](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg)
```

With token:
```markdown
[![codecov](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg)](https://codecov.io/gh/YOUR_USERNAME/backtrader_web)
```

### Separate Coverage Badges

Backend:
```markdown
![Backend Coverage](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg?flag=backend)
```

Frontend:
```markdown
![Frontend Coverage](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg?flag=frontend)
```

## Quality Metrics

### Project Status
```markdown
![Project Status](https://img.shields.io/badge/status-active-success.svg)
```

### Maintenance
```markdown
![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)
```

### License
```markdown
![License](https://img.shields.io/github/license/YOUR_USERNAME/backtrader_web)
```

## Technology Stack

### Python Version
```markdown
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
```

### Node Version
```markdown
![Node](https://img.shields.io/badge/node-20%2B-green.svg)
```

### Framework Versions
```markdown
![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-teal.svg)
![Vue](https://img.shields.io/badge/Vue-3.4%2B-brightgreen.svg)
```

## Additional Badges

### GitHub Issues
```markdown
![Issues](https://img.shields.io/github/issues/YOUR_USERNAME/backtrader_web)
```

### Pull Requests
```markdown
![PRs](https://img.shields.io/github/issues-pr/YOUR_USERNAME/backtrader_web)
```

### Last Commit
```markdown
![Last Commit](https://img.shields.io/github/last-commit/YOUR_USERNAME/backtrader_web)
```

### Repo Size
```markdown
![Repo Size](https://img.shields.io/github/repo-size/YOUR_USERNAME/backtrader_web)
```

## Example README Section

```markdown
# Backtrader Web

![CI - Quality Checks](https://github.com/YOUR_USERNAME/backtrader_web/workflows/CI%20-%20Quality%20Checks/badge.svg)
![E2E Tests](https://github.com/YOUR_USERNAME/backtrader_web/workflows/E2E%20-%20End-to-End%20Tests/badge.svg)
[![codecov](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg)](https://codecov.io/gh/YOUR_USERNAME/backtrader_web)
![License](https://img.shields.io/github/license/YOUR_USERNAME/backtrader_web)

A quantitative trading platform with Backtrader integration.

## Status

| Pipeline | Status |
|----------|--------|
| CI Quality Checks | ![CI](https://github.com/YOUR_USERNAME/backtrader_web/workflows/CI%20-%20Quality%20Checks/badge.svg) |
| E2E Tests | ![E2E](https://github.com/YOUR_USERNAME/backtrader_web/workflows/E2E%20-%20End-to-End%20Tests/badge.svg) |
| Backend Coverage | ![Backend](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg?flag=backend) |
| Frontend Coverage | ![Frontend](https://codecov.io/gh/YOUR_USERNAME/backtrader_web/branch/master/graph/badge.svg?flag=frontend) |
```

## Custom Badge Creation

For custom badges, use Shields.io:

```markdown
https://img.shields.io/badge/<label>-<message>-<color>
```

Example:
```markdown
![Custom](https://img.shields.io/badge/build-passing-brightgreen)
```

## Updating Badges

Remember to replace `YOUR_USERNAME` with your actual GitHub username in all badge URLs.
