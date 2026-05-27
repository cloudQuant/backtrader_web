import sys

from app.services.akshare import execution as _execution

sys.modules[__name__] = _execution
