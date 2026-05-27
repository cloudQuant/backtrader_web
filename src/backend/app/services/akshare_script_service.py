import sys

from app.services.akshare import script as _script

sys.modules[__name__] = _script
