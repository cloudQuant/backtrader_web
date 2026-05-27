import sys

from app.services.gateway import runtime as _runtime

sys.modules[__name__] = _runtime
