import sys

from app.services.optimization import trial_runner as _trial_runner

sys.modules[__name__] = _trial_runner
