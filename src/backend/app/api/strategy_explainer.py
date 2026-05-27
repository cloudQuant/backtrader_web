import sys

from app.api.strategy import explainer as _explainer

sys.modules[__name__] = _explainer
