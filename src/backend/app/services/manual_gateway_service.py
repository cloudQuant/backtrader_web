import sys
from app.services.gateway import manual as _manual
sys.modules[__name__] = _manual
