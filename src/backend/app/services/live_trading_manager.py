import sys

from app.services.live_trading import manager as _manager

sys.modules[__name__] = _manager
