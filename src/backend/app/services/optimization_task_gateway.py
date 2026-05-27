import sys

from app.services.optimization import task_gateway as _task_gateway

sys.modules[__name__] = _task_gateway
