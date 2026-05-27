import sys

from app.api.data import realtime as _realtime

sys.modules[__name__] = _realtime
