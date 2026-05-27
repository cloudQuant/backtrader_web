import sys

from app.api.strategy import version as _version

sys.modules[__name__] = _version
