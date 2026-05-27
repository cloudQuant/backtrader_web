import sys

from app.api.data import governance as _governance

sys.modules[__name__] = _governance
