"""
App package initialization.

Provides a single import surface for submodules.
"""

# Backend modules
from . import config
from . import db
from . import services
from . import api
from . import utils

__all__ = [
    "config",
    "db",
    "services",
    "api",
    "utils",
]
