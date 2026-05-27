import sys

from app.api.data import topics as _topics

sys.modules[__name__] = _topics
