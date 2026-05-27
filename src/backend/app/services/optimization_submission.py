import sys

from app.services.optimization import submission as _submission

sys.modules[__name__] = _submission
