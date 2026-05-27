import sys

from app.services.strategy import version as _version

sys.modules[__name__] = _version
