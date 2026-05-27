import sys

from app.services.live_trading import service as _service

sys.modules[__name__] = _service
