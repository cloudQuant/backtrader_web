"""
API dependencies.
"""

import sys

from app.api import _dependencies

sys.modules[__name__] = _dependencies
