import sys

from app.services.optimization import async_runner as _async_runner

sys.modules[__name__] = _async_runner
