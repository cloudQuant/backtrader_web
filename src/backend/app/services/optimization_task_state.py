import sys

from app.services.optimization import task_state as _task_state

sys.modules[__name__] = _task_state
