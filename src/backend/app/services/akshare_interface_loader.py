import sys

from app.services.akshare import interface_loader as _interface_loader

sys.modules[__name__] = _interface_loader
