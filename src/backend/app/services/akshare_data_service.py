import sys

from app.services.akshare import data as _data

sys.modules[__name__] = _data
