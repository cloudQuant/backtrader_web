import sys

from app.services.gateway import launch_builder as _launch_builder

sys.modules[__name__] = _launch_builder
