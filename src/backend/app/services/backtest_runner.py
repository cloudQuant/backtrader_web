import sys

from app.services.backtest import runner as _runner

sys.modules[__name__] = _runner
