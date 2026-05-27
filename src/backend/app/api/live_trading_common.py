import sys

from app.api.live_trading import _shared

sys.modules[__name__] = _shared
