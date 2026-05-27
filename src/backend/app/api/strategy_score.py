import sys

from app.api.strategy import score as _score

sys.modules[__name__] = _score
