"""Plugin system for extensible fincore framework.

Allows users to register:
- Custom metrics
- Custom visualization backends
- Event hooks
- Custom risk models
- Custom optimization objectives

All registries are stored in :mod:`fincore.plugin.registry` which is the
single source of truth.
"""

from __future__ import annotations

# Re-export everything from registry (single source of truth)
from fincore.plugin.registry import (
    clear_registry,
    execute_hooks,
    get_metric,
    get_viz_backend,
    list_hooks,
    list_metrics,
    list_viz_backends,
    register_hook,
    register_metric,
    register_viz_backend,
)

__all__ = [
    "clear_registry",
    "execute_hooks",
    "get_metric",
    "get_viz_backend",
    "list_hooks",
    "list_metrics",
    "list_viz_backends",
    "register_hook",
    "register_metric",
    "register_viz_backend",
]
