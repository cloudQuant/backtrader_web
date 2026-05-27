import sys

from app.services.strategy import runtime_support as _runtime_support

sys.modules[__name__] = _runtime_support
