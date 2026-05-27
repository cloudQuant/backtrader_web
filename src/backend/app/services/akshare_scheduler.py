import sys

from app.services.akshare import scheduler as _scheduler

sys.modules[__name__] = _scheduler
