import sys

from app.services.backtest import service as _service

sys.modules[__name__] = _service
