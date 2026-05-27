import sys

from app.services.gateway import health as _health

sys.modules[__name__] = _health
