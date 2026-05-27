import sys

from app.services.live_trading import instance as _instance

sys.modules[__name__] = _instance
