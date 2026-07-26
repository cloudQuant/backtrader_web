import sys

from app.api.live_trading import api as _api

sys.modules[__name__] = _api
