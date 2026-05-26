from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass, field

from app.services.ai_router.ollama_adapter import check_ollama_health
from app.services.ai_router.providers import AIProviderSpec, get_default_provider_specs


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    display_name: str
    provider_type: str
    available: bool
    base_url: str | None = None
    models: list[str] = field(default_factory=list)
    error: str | None = None

    def model_dump(self) -> dict:
        return asdict(self)


class AIProviderHealthService:
    def __init__(self, provider_specs: list[AIProviderSpec] | None = None) -> None:
        self.provider_specs = provider_specs or get_default_provider_specs()

    async def check_all(self) -> list[ProviderHealth]:
        results = []
        for spec in self.provider_specs:
            results.append(await self._check_provider(spec))
        return results

    async def _check_provider(self, spec: AIProviderSpec) -> ProviderHealth:
        if spec.name == "ollama":
            return await asyncio.to_thread(self._check_ollama, spec)
        return self._check_configured_provider(spec)

    def _check_ollama(self, spec: AIProviderSpec) -> ProviderHealth:
        health = check_ollama_health(base_url=spec.base_url or "http://localhost:11434")
        models = health.models or list(spec.models)
        return ProviderHealth(
            name=spec.name,
            display_name=spec.display_name,
            provider_type=spec.provider_type,
            base_url=health.base_url,
            available=health.available,
            models=models,
            error=health.error,
        )

    def _check_configured_provider(self, spec: AIProviderSpec) -> ProviderHealth:
        configured = True
        error = None
        if spec.api_key_env and not os.getenv(spec.api_key_env):
            configured = False
            error = f"{spec.api_key_env} not configured"
        return ProviderHealth(
            name=spec.name,
            display_name=spec.display_name,
            provider_type=spec.provider_type,
            base_url=spec.base_url,
            available=configured,
            models=list(spec.models),
            error=error,
        )


def build_provider_health_payload(providers: list[ProviderHealth]) -> dict:
    available = sum(1 for provider in providers if provider.available)
    return {
        "summary": {
            "total": len(providers),
            "available": available,
            "unavailable": len(providers) - available,
        },
        "providers": [provider.model_dump() for provider in providers],
    }
