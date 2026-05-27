import sys

from app.services.optimization import execution_manager as _execution_manager

sys.modules[__name__] = _execution_manager
