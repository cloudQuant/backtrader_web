from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.ai_provider_registry import (
    DEFAULT_PROVIDER_REGISTRY,
)
from app.ai_provider_registry import (
    get_default_provider_registry as _get_default_provider_registry,
)
from app.services.ai_router.provider_config_store import get_effective_provider_registry


@dataclass(frozen=True)
class AIProviderSpec:
    name: str
    display_name: str
    provider_type: str
    base_url: str | None = None
    api_key_env: str | None = None
    api_key: str | None = None
    models: tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True


def get_default_provider_registry() -> dict[str, dict[str, Any]]:
    return _get_default_provider_registry()


def build_provider_specs(
    provider_registry: Mapping[str, Mapping[str, Any]] | None,
) -> list[AIProviderSpec]:
    registry = get_effective_provider_registry(provider_registry or DEFAULT_PROVIDER_REGISTRY)
    specs: list[AIProviderSpec] = []
    for name, raw_config in registry.items():
        enabled = _coerce_enabled(raw_config.get("enabled", True))
        if not enabled:
            continue
        models = _coerce_models(raw_config.get("models"))
        # Existing deployments may override ``AI_PROVIDERS`` with a model list
        # created before GLM-5.2 was introduced. Keep that configuration while
        # making the product default selectable without a manual .env edit.
        if str(name) == "volcengine_ark" and "glm-5.2" not in models:
            models.append("glm-5.2")
        if not models:
            continue
        specs.append(
            AIProviderSpec(
                name=str(name),
                display_name=str(
                    raw_config.get("display_name")
                    or raw_config.get("name")
                    or _humanize_provider_name(str(name))
                ),
                provider_type=str(
                    raw_config.get("provider_type") or _default_provider_type(str(name))
                ),
                base_url=_optional_str(raw_config.get("base_url")),
                api_key_env=_optional_str(raw_config.get("api_key_env")),
                api_key=_optional_str(raw_config.get("api_key")),
                models=tuple(models),
                enabled=enabled,
            )
        )
    return specs


def get_default_provider_specs() -> list[AIProviderSpec]:
    try:
        from app.config import get_settings

        registry = get_settings().AI_PROVIDERS
    except Exception:
        registry = DEFAULT_PROVIDER_REGISTRY
    return build_provider_specs(registry)


def get_provider_api_key(spec: AIProviderSpec) -> str | None:
    if spec.api_key:
        return spec.api_key
    if not spec.api_key_env:
        return None
    return get_secret_value(spec.api_key_env)


def is_provider_configured(spec: AIProviderSpec) -> bool:
    if spec.api_key_env and not get_provider_api_key(spec):
        return False
    if spec.provider_type == "openai_compatible" and not spec.base_url:
        return False
    return True


def get_secret_value(env_name: str) -> str | None:
    value = os.getenv(env_name)
    if value:
        return value
    return _read_env_file_values().get(env_name)


def _coerce_models(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _coerce_enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off", "disabled"}
    return bool(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _humanize_provider_name(name: str) -> str:
    return name.replace("_", " ").title()


def _default_provider_type(name: str) -> str:
    if name in {"openai", "anthropic", "ollama", "together", "groq"}:
        return "litellm"
    return "openai_compatible"


@lru_cache(maxsize=1)
def _read_env_file_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in _env_file_candidates():
        if not path.is_file():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                parsed = _parse_env_line(raw_line)
                if parsed is not None:
                    key, value = parsed
                    values.setdefault(key, value)
        except OSError:
            continue
    return values


def _env_file_candidates() -> tuple[Path, ...]:
    repo_root = Path(__file__).resolve().parents[5]
    return (Path.cwd() / ".env", repo_root / ".env")


def _parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value
