import sys
from app.services.backtest import manager as _manager
sys.modules[__name__] = _manager
