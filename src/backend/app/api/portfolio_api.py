import sys

from app.api.portfolio import api as _api

sys.modules[__name__] = _api
