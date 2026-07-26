# ADR-004: Graceful Shutdown

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** AI for Investor Team

## Context

During deployments, the application would terminate immediately upon receiving SIGTERM,
causing:

- In-flight HTTP requests to fail with connection reset errors
- Active WebSocket connections (live backtest progress, market data streams) to drop
  without notification
- Running backtest tasks to be interrupted mid-execution
- Load balancer health checks to continue routing traffic to a dying instance

This resulted in user-visible errors during every deployment and potential data
corruption for backtests that were writing results at termination time.

## Decision

Implement a `GracefulShutdownManager` integrated with FastAPI's lifespan events:

1. **Health check transitions to 503** — on SIGTERM, `/health` immediately returns 503
   so the load balancer stops routing new traffic
2. **Drain period** — configurable timeout (default: 30s) to allow in-flight requests
   to complete
3. **WebSocket close frames** — active WebSocket connections receive a close frame with
   code 1001 (Going Away) and a human-readable reason
4. **Task completion** — running backtest tasks are given time to reach a checkpoint
   before forced termination
5. **Force shutdown** — after the drain timeout, remaining connections are forcibly closed

```python
class GracefulShutdownManager:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.is_shutting_down = False
        self._active_connections: set[WebSocket] = set()

    async def shutdown(self):
        self.is_shutting_down = True
        await self._close_websockets()
        await self._wait_for_requests(timeout=self.timeout)
```

Configuration:
- `SHUTDOWN_TIMEOUT`: Drain period in seconds (default: 30)
- `SHUTDOWN_WEBSOCKET_CLOSE_CODE`: WebSocket close code (default: 1001)

## Consequences

### Positive

- Zero-downtime deployments are now achievable with rolling updates
- Users see no errors during routine deployments
- WebSocket clients receive proper close frames and can reconnect to a new instance
- Backtest tasks can checkpoint their progress before shutdown

### Negative

- Adds complexity to the application lifespan management
- Deployment time increases by up to `SHUTDOWN_TIMEOUT` seconds per instance
- Developers must register long-running tasks with the shutdown manager
- Edge case: if a request takes longer than the drain timeout, it is still terminated

### Neutral

- Compatible with Kubernetes, Docker Compose, and systemd deployment models
- No change to the application behavior during normal operation
- Health check endpoint behavior is unchanged when not shutting down
