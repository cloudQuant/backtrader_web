import sys

from app.services.akshare import interface as _interface

sys.modules[__name__] = _interface
