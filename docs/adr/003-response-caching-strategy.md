# ADR-003: Response Caching Strategy

**Status:** Accepted
**Date:** 2026-05-20
**Deciders:** Backtrader Web Team

## Context

Several read-heavy API endpoints (strategy listings, backtest results, market data
summaries) hit the database on every request despite data changing infrequently. Under
load, this creates unnecessary database pressure and increases response latency for
data that may not have changed in hours.

Profiling showed that 70%+ of API calls were reads to data that updates at most once
per minute (market summaries) or only on user action (strategy configs, completed
backtest results).

## Decision

Implement a custom `@cache_response` decorator with a dual-backend caching strategy:

1. **Primary backend: Redis** — shared cache across multiple worker processes, supports
   TTL-based expiration and pattern-based invalidation
2. **Fallback backend: In-memory (LRU)** — used when Redis is unavailable or in
   development/testing environments

Usage:

```python
@router.get("/strategies")
@cache_response(ttl=300, key_prefix="strategies", vary_on=["user_id"])
async def list_strategies(user_id: int = Depends(get_current_user_id)):
    return await strategy_service.get_user_strategies(user_id)
```

Cache invalidation is explicit via service-layer hooks:

```python
async def update_strategy(self, strategy_id: int, data: StrategyUpdate):
    result = await self.repo.update(strategy_id, data)
    await cache.invalidate(f"strategies:user:{result.user_id}:*")
    return result
```

Configuration via environment variables:
- `CACHE_BACKEND`: `redis` | `memory` (default: `memory`)
- `CACHE_REDIS_URL`: Redis connection string
- `CACHE_DEFAULT_TTL`: Default TTL in seconds (default: 300)

## Consequences

### Positive

- Significant reduction in database load for read-heavy endpoints
- Sub-millisecond response times for cached data
- Graceful degradation — falls back to memory cache if Redis is down
- Per-user cache isolation via `vary_on` parameter prevents data leaks

### Negative

- Cache invalidation must be explicitly handled in service layer — forgetting to
  invalidate leads to stale data
- Adds Redis as an optional infrastructure dependency
- Debugging cache-related issues requires understanding the invalidation flow
- Memory cache in multi-worker deployments can serve stale data

### Neutral

- Cache keys are deterministic and inspectable via Redis CLI
- No change to API contracts — caching is transparent to clients
- Cache miss path is identical to the previous uncached behavior
