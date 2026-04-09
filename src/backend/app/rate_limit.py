"""Shared rate limiter configuration."""

from pathlib import Path

from slowapi import Limiter
from slowapi.util import get_remote_address

_SLOWAPI_CONFIG_FILE = Path(__file__).resolve().parents[1] / ".slowapi.env"

limiter = Limiter(key_func=get_remote_address, config_filename=str(_SLOWAPI_CONFIG_FILE))
