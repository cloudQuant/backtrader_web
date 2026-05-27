import sys

from app.services.akshare import scheduler_service as _scheduler_service

sys.modules[__name__] = _scheduler_service
