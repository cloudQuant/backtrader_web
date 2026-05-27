import sys

from app.api.data import deps as _deps

sys.modules[__name__] = _deps
