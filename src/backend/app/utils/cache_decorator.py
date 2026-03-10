"""
Cache decorator for API responses.

Automatically caches API responses to Redis/Memory cache.
"""

import hashlib
import json
from functools import wraps
from typing import Any, Callable, List, Optional

from app.db.cache import get_cache


def cache_response(
    ttl: int = 300, key_prefix: str = "api", vary_by_params: Optional[List[str]] = None
):
    """
    Decorator to cache API responses.

    Args:
        ttl: Time-to-live in seconds (default: 300 = 5 minutes)
        key_prefix: Prefix for cache key (default: "api")
        vary_by_params: List of parameter names to include in cache key
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [key_prefix, func.__name__]

            # Add varying parameters to key if specified
            if vary_by_params:
                for param in vary_by_params:
                    if param in kwargs:
                        key_parts.append(f"{param}={kwargs[param]}")

            cache_key = ":".join(key_parts)

            # Try to get from cache
            cache = get_cache()
            cached_response = await cache.get(cache_key)

            if cached_response is not None:
                return cached_response

            # Execute function
            result = await func(*args, **kwargs)

            # Cache the result
            await cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


# Convenience function to generate cache key for complex objects
def generate_cache_key(prefix: str, data: Any) -> str:
    """Generate a stable cache key from data object."""
    data_str = json.dumps(data, sort_keys=True)
    hash_obj = hashlib.md5(data_str.encode())
    return f"{prefix}:{hash_obj.hexdigest()}"
