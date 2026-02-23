"""
App package initialization.

Provides a single import surface for submodules.
"""

# Backend modules
from . import api, config, db, services, utils

__all__ = [
    "config",
    "db",
    "services",
    "api",
    "utils",
]
