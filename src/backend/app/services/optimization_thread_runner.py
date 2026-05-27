import sys

from app.services.optimization import thread_runner as _thread_runner

sys.modules[__name__] = _thread_runner
