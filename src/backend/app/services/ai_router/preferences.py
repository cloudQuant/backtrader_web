from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from app.db.session_provider import unit_of_work
from app.models.user import User
from app.services.ai_router.providers import AIProviderSpec, get_default_provider_specs


@dataclass(frozen=True)
class AIModelOption:
    provider: str
    model: str
    display_name: str

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AIProviderOption:
    name: str
    display_name: str
    provider_type: str
    base_url: str | None
    models: list[str]

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedAIModelPreference:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None


class AIModelPreferenceService:
    def __init__(self, provider_specs: list[AIProviderSpec] | None = None) -> None:
        self.provider_specs = provider_specs or get_default_provider_specs()

    def get_available_models_payload(self, user: User) -> dict:
        providers = [self._provider_option(spec).model_dump() for spec in self.provider_specs]
        models = [option.model_dump() for option in self._model_options()]
        return {
            "providers": providers,
            "models": models,
            "preferences": self.get_preferences(user),
        }

    def get_preferences(self, user: User) -> dict[str, str | None]:
        return {
            "provider": getattr(user, "ai_preferred_provider", None),
            "model": getattr(user, "ai_preferred_model", None),
        }

    def is_model_available(self, *, provider: str | None, model: str | None) -> bool:
        if not provider and not model:
            return True
        return any(
            option.provider == provider and option.model == model
            for option in self._model_options()
        )

    async def resolve_for_user(self, user_id: str | None) -> ResolvedAIModelPreference | None:
        if not user_id:
            return None
        async with unit_of_work() as session:
            user = await session.get(User, user_id)
            if user is None:
                return None
            provider = getattr(user, "ai_preferred_provider", None)
            model = getattr(user, "ai_preferred_model", None)
        if not self.is_model_available(provider=provider, model=model):
            return None
        spec = self._find_provider(str(provider))
        if spec is None:
            return None
        api_key = os.getenv(spec.api_key_env) if spec.api_key_env else None
        return ResolvedAIModelPreference(
            provider=spec.provider_type,
            model=str(model),
            base_url=spec.base_url,
            api_key=api_key,
        )

    def resolve_model_key(self, model_key: str | None) -> ResolvedAIModelPreference | None:
        if not model_key or "::" not in model_key:
            return None
        provider, model = model_key.split("::", 1)
        if not self.is_model_available(provider=provider, model=model):
            return None
        spec = self._find_provider(provider)
        if spec is None:
            return None
        api_key = os.getenv(spec.api_key_env) if spec.api_key_env else None
        return ResolvedAIModelPreference(
            provider=spec.provider_type,
            model=model,
            base_url=spec.base_url,
            api_key=api_key,
        )

    def _provider_option(self, spec: AIProviderSpec) -> AIProviderOption:
        return AIProviderOption(
            name=spec.name,
            display_name=spec.display_name,
            provider_type=spec.provider_type,
            base_url=spec.base_url,
            models=list(spec.models),
        )

    def _model_options(self) -> list[AIModelOption]:
        options: list[AIModelOption] = []
        for spec in self.provider_specs:
            for model in spec.models:
                options.append(
                    AIModelOption(
                        provider=spec.name,
                        model=model,
                        display_name=f"{spec.display_name} / {model}",
                    )
                )
        return options

    def _find_provider(self, name: str) -> AIProviderSpec | None:
        return next((spec for spec in self.provider_specs if spec.name == name), None)
