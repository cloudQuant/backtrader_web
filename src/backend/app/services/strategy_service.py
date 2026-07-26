import sys

from app.services.strategy import core as _core

sys.modules[__name__] = _core
