import sys

from app.services.backtest import analyzers as _analyzers

sys.modules[__name__] = _analyzers
