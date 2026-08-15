"""In-process concurrency controls for approved multi-asset source collection.

The database lease protects a schedule fire across processes.  This limiter is
the complementary per-process guard: it prevents one approved provider from
being overwhelmed when several interactive or scheduled requests collect at
the same time.  An undeclared or multi-source adapter intentionally shares a
single conservative bucket rather than creating unbounded provider keys.
"""

from __future__ import annotations

import asyncio
import re
import weakref
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from app.config import get_settings

_SAFE_SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_UNDECLARED_SOURCE_BUCKET = "UNDECLARED"


class AssetResearchSourceConcurrencyLimiter:
    """Bound simultaneous collection calls for each server-declared source.

    Semaphores are scoped to the running event loop so pytest's function-scoped
    loops and an application loop never share an asyncio primitive.  The key
    is only derived from adapter declarations, never from a provider payload
    or user request.
    """

    def __init__(self, *, max_per_source: int) -> None:
        if max_per_source < 1:
            raise ValueError("max_per_source must be at least 1")
        self.max_per_source = max_per_source
        self._semaphores: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, dict[str, asyncio.Semaphore]
        ] = weakref.WeakKeyDictionary()

    @staticmethod
    def bucket_for(source_id: str | None) -> str:
        """Return one bounded, server-safe bucket identifier."""
        normalized = str(source_id or "").strip()
        if _SAFE_SOURCE_ID.fullmatch(normalized):
            return normalized
        return _UNDECLARED_SOURCE_BUCKET

    @asynccontextmanager
    async def acquire(self, source_id: str | None) -> AsyncIterator[None]:
        """Acquire the source-specific permit for one collection attempt."""
        loop = asyncio.get_running_loop()
        buckets = self._semaphores.setdefault(loop, {})
        bucket = self.bucket_for(source_id)
        semaphore = buckets.get(bucket)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.max_per_source)
            buckets[bucket] = semaphore
        async with semaphore:
            yield


@lru_cache(maxsize=1)
def get_asset_research_source_concurrency_limiter() -> AssetResearchSourceConcurrencyLimiter:
    """Return the application-wide limiter using the configured provider cap."""
    return AssetResearchSourceConcurrencyLimiter(
        max_per_source=get_settings().ASSET_RESEARCH_SOURCE_MAX_CONCURRENCY
    )
