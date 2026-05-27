import sys

from app.services.gateway import preset as _preset

sys.modules[__name__] = _preset
