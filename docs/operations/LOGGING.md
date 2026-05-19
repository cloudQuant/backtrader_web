# Enhanced Logging System Documentation

## Overview

The backtrader_web framework includes a comprehensive logging system built on top of [loguru](https://github.com/Delgan/loguru), providing structured logging, sensitive data filtering, and multiple log outputs.

## Features

### 1. Structured JSON Logging
- JSON format for production environments
- Easy integration with log aggregation tools (ELK, Splunk, etc.)
- Automatic timestamp formatting

### 2. Sensitive Data Filtering
- Automatically masks passwords, tokens, API keys, and credentials
- Works with nested dictionaries and lists
- Configurable sensitive patterns

### 3. Multiple Log Files
- `app_YYYY-MM-DD.log` - General application logs (30 days retention)
- `errors_YYYY-MM-DD.log` - Error logs only (90 days retention)
- `audit_YYYY-MM-DD.log` - Security audit events (365 days retention)
- `backtest_YYYY-MM-DD.log` - Backtest execution logs (60 days retention)

### 4. Request/Task Context Tracking
- Automatic request ID generation
- User ID tracking
- Task ID binding for async operations

### 5. Audit Logging
- Specialized audit logger for security events
- Login/logout tracking
- Permission denied events
- Strategy access logging

## Usage

### Basic Logging

```python
from app.utils.logger import get_logger

logger = get_logger(__name__)

logger.info("Processing started")
logger.debug("Debug information", extra_data="value")
logger.warning("Warning condition")
logger.error("Error occurred", error_code=500)
logger.critical("Critical failure")
```

### With Request Context

```python
from app.utils.logger import bind_request_context
from fastapi import Request

async def my_endpoint(request: Request):
    # Generate request ID
    request_id = str(uuid.uuid4())[:8]

    # Bind context for all logs in this request
    logger = bind_request_context(request_id, user_id="user-123")

    logger.info("Processing request")  # Automatically includes request_id and user_id
```

### With Task Context

```python
from app.utils.logger import bind_task_context

async def run_backtest(task_id: str, user_id: str):
    # Bind task context
    logger = bind_task_context(task_id, user_id=user_id, task_type="backtest")

    logger.info("Backtest started")
    # ... processing ...
    logger.info("Backtest completed", duration=5.5)
```

### Audit Logging

```python
from app.utils.logger import audit_logger

# Log login event
audit_logger.log_login("user-123", success=True, ip="192.168.1.1")

# Log logout
audit_logger.log_logout("user-123")

# Log permission denied
audit_logger.log_permission_denied("user-123", resource="strategy-1", action="delete")

# Log strategy access
audit_logger.log_strategy_access("user-123", strategy_id="strategy-1", action="view")

# Log backtest events
audit_logger.log_backtest_start("user-123", "task-456", "strategy-1")
audit_logger.log_backtest_complete("user-123", "task-456", duration=5.5, success=True)
```

### Log Context Manager

```python
from app.utils.logger import LogContext

with LogContext(request_id="req-123", operation="export"):
    logger.info("Starting operation")
    # All logs here automatically include the context
```

### Conditional Logging with Context

```python
from app.utils.logger import log_with_context

log_with_context(
    "User action completed",
    level="INFO",
    user_id="user-123",
    action="delete_strategy",
    strategy_id="strategy-1"
)
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DEBUG` | Enable debug mode (colorful logs) | `True` |
| `LOG_LEVEL` | Minimum log level | `INFO` |
| `LOG_DIR` | Log directory | `logs` |

### Log Levels

- `DEBUG` - Detailed information for diagnosing problems
- `INFO` - General information about program execution
- `WARNING` - Something unexpected happened
- `ERROR` - Serious error occurred
- `CRITICAL` - Critical error, program may not continue

## Sensitive Data Filtering

The following patterns are automatically filtered from logs:

- `password`
- `secret`
- `token`
- `api_key`
- `access_token`
- `refresh_token`
- `authorization`
- `credential`

Example:
```python
# This input:
{"username": "test", "password": "secret123", "api_key": "sk-123456"}

# Becomes:
{"username": "test", "password": "se******23", "api_key": "sk******56"}
```

## Middleware Integration

The logging system is automatically integrated via FastAPI middleware:

1. **LoggingMiddleware** - Logs all HTTP requests/responses with timing
2. **AuditLoggingMiddleware** - Tracks authentication and authorization events
3. **PerformanceLoggingMiddleware** - Tracks slow requests (>5 seconds)

## Log File Locations

```
logs/
├── app_2026-02-18.log          # All application logs
├── errors_2026-02-18.log       # Error logs only
├── audit_2026-02-18.log         # Security audit logs
└── backtest_2026-02-18.log      # Backtest execution logs
```

## Best Practices

1. **Always use context for user actions**: Include `user_id` when logging user-related events
2. **Use appropriate log levels**:
   - DEBUG for development troubleshooting
   - INFO for normal operation tracking
   - WARNING for recoverable issues
   - ERROR for failures requiring attention
   - CRITICAL for system-threatening issues
3. **Never log sensitive data directly**: The filtering system helps, but be cautious
4. **Use audit logger for security events**: Ensures proper retention and tracking

## Examples

### In API Endpoints

```python
from app.utils.logger import get_logger, audit_logger
from fastapi import Request

router = APIRouter()
logger = get_logger(__name__)

@router.post("/strategy")
async def create_strategy(request: Request, data: StrategyCreate):
    user_id = request.state.user_id
    logger.info("Creating strategy", user_id=user_id, strategy_name=data.name)

    strategy = await service.create_strategy(data)

    audit_logger.log_strategy_access(user_id, strategy.id, "create")
    return strategy
```

### In Services

```python
from app.utils.logger import bind_task_context, get_logger

logger = get_logger(__name__)

class BacktestService:
    async def run_backtest(self, user_id: str, request: BacktestRequest):
        task_id = str(uuid.uuid4())

        # Bind task context
        task_logger = bind_task_context(task_id, user_id=user_id, task_type="backtest")
        task_logger.info("Backtest initialized")

        # Run backtest...
        task_logger.info("Backtest completed", duration=duration)

        return result
```

### Error Logging

```python
try:
    result = await risky_operation()
except Exception as e:
    logger.error("Operation failed", error=str(e), error_type=type(e).__name__)
    logger.exception("Full traceback")  # Includes stack trace
    raise
```

## Troubleshooting

### Logs not appearing
1. Check log directory exists: `ls logs/`
2. Verify log level: `DEBUG` mode shows all logs
3. Check file permissions

### Missing context in logs
1. Ensure `bind_request_context()` or `bind_task_context()` is called
2. Verify context is passed through function calls

### Performance issues
1. Reduce log level to `WARNING` or `ERROR` in production
2. Check disk space for rotated logs
3. Consider using async logging for high-volume scenarios
