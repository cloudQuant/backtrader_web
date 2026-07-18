from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.utils.backend_data_paths import get_backend_data_path
from app.utils.secure_file import write_private_text

_PROVIDER_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_ENCRYPTED_PREFIX = "fernet:"


def get_provider_config_path() -> Path:
    override = os.getenv("AI_PROVIDER_CONFIG_PATH")
    if override:
        return Path(override).expanduser()
    return get_backend_data_path("ai_provider_config.json")


def get_effective_provider_registry(
    base_registry: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    registry = {
        str(key): dict(value)
        for key, value in (base_registry or {}).items()
        if isinstance(value, Mapping)
    }
    for key, override in _load_provider_overrides().items():
        if _is_deleted(override):
            registry.pop(key, None)
            continue
        merged = dict(registry.get(key, {}))
        merged.update(override)
        registry[key] = merged
    return registry


def list_provider_configs(
    base_registry: Mapping[str, Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    raw_overrides = _read_raw_config().get("providers", {})
    effective = get_effective_provider_registry(base_registry)
    items: list[dict[str, Any]] = []
    for provider_key in sorted(effective):
        raw = effective[provider_key]
        source = "override" if provider_key in raw_overrides else "default"
        items.append(_to_public_config(provider_key, raw, source=source))
    return items


def save_provider_config(
    provider_key: str,
    payload: Mapping[str, Any],
    *,
    base_registry: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    key = _validate_provider_key(provider_key)
    raw_config = _read_raw_config()
    providers = raw_config.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        raw_config["providers"] = providers

    existing = dict(providers.get(key) or {})
    base = dict((base_registry or {}).get(key) or {})

    next_config: dict[str, Any] = {
        "display_name": _required_text(payload.get("display_name"), "display_name", max_length=120),
        "provider_type": _provider_type(payload.get("provider_type")),
        "base_url": _optional_text(payload.get("base_url"), max_length=500),
        "api_key_env": _optional_text(payload.get("api_key_env"), max_length=120),
        "models": _models(payload.get("models")),
        "enabled": bool(payload.get("enabled", True)),
    }

    api_key = _optional_text(payload.get("api_key"), max_length=4096)
    if api_key:
        next_config["api_key"] = _encrypt_secret(api_key)
    elif "api_key" in existing:
        next_config["api_key"] = existing["api_key"]

    providers[key] = next_config
    _write_raw_config(raw_config)

    effective = dict(base)
    effective.update(_decrypt_provider_config(next_config))
    return _to_public_config(key, effective, source="override")


def delete_provider_config(
    provider_key: str,
    *,
    base_registry: Mapping[str, Mapping[str, Any]] | None,
) -> None:
    key = _validate_provider_key(provider_key)
    raw_config = _read_raw_config()
    providers = raw_config.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        raw_config["providers"] = providers

    if key in (base_registry or {}):
        providers[key] = {"deleted": True}
    else:
        providers.pop(key, None)
    _write_raw_config(raw_config)


def _load_provider_overrides() -> dict[str, dict[str, Any]]:
    raw = _read_raw_config().get("providers", {})
    if not isinstance(raw, dict):
        return {}
    overrides: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            continue
        try:
            provider_key = _validate_provider_key(str(key))
        except ValueError:
            continue
        overrides[provider_key] = _decrypt_provider_config(value)
    return overrides


def _read_raw_config() -> dict[str, Any]:
    path = get_provider_config_path()
    if not path.is_file():
        return {"providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"providers": {}}
    return data if isinstance(data, dict) else {"providers": {}}


def _write_raw_config(payload: Mapping[str, Any]) -> None:
    path = get_provider_config_path()
    write_private_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    )


def _decrypt_provider_config(config: Mapping[str, Any]) -> dict[str, Any]:
    decrypted = dict(config)
    api_key = decrypted.get("api_key")
    if isinstance(api_key, str) and api_key.startswith(_ENCRYPTED_PREFIX):
        decrypted["api_key"] = _decrypt_secret(api_key)
    return decrypted


def _to_public_config(provider_key: str, raw: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    direct_key = _optional_text(raw.get("api_key"), max_length=4096)
    api_key_env = _optional_text(raw.get("api_key_env"), max_length=120)
    return {
        "provider": provider_key,
        "display_name": str(raw.get("display_name") or provider_key),
        "provider_type": str(raw.get("provider_type") or "openai_compatible"),
        "base_url": _optional_text(raw.get("base_url"), max_length=500),
        "api_key_env": api_key_env,
        "api_key_configured": bool(direct_key or (api_key_env and os.getenv(api_key_env))),
        "models": _models(raw.get("models")),
        "enabled": _enabled(raw.get("enabled", True)),
        "source": source,
    }


def _is_deleted(config: Mapping[str, Any]) -> bool:
    return _enabled(config.get("deleted", False))


def _encrypt_secret(value: str) -> str:
    return f"{_ENCRYPTED_PREFIX}{_fernet().encrypt(value.encode('utf-8')).decode('utf-8')}"


def _decrypt_secret(value: str) -> str:
    token = value.removeprefix(_ENCRYPTED_PREFIX)
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def _fernet() -> Fernet:
    secret = get_settings().SECRET_KEY.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _validate_provider_key(provider_key: str) -> str:
    key = provider_key.strip().lower()
    if not _PROVIDER_KEY_RE.fullmatch(key):
        raise ValueError("provider key must be 2-64 chars: lowercase letters, numbers, _ or -")
    return key


def _required_text(value: object, field: str, *, max_length: int) -> str:
    text = _optional_text(value, max_length=max_length)
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _optional_text(value: object, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length:
        raise ValueError(f"value exceeds {max_length} characters")
    return text


def _provider_type(value: object) -> str:
    provider_type = _required_text(value, "provider_type", max_length=50)
    if provider_type not in {"litellm", "openai_compatible"}:
        raise ValueError("provider_type must be litellm or openai_compatible")
    return provider_type


def _models(value: object) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        items = []
    models = [item for item in items if item]
    if not models:
        raise ValueError("models must contain at least one model")
    if len(models) > 100:
        raise ValueError("models cannot contain more than 100 entries")
    return models


def _enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off", "disabled"}
    return bool(value)
