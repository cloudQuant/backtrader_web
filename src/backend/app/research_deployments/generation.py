"""Opt-in composition root for the real protocol-v2 GENERATE worker.

This module is deliberately separate from the diagnostic Explorer factory.
It only composes reviewed, server-owned deployment configuration: neither an
API request nor a user AI-provider preference can select its endpoint, model,
prompt, quota policy, dataset resolver, or materialization environment.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from pydantic import SecretStr

from app.config import Settings, get_settings
from app.services.research.canonical import normalize_payload
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.deterministic_executor import DeterministicClarifyExecutor
from app.services.research.generation_executor import (
    GenerationExecutorPolicy,
    ResearchGenerationExecutor,
)
from app.services.research.generation_materialization import (
    GenerationMaterializationPolicy,
    ResearchGenerationMaterializer,
)
from app.services.research.llm_gateway import LlmGateway, ModelCatalog
from app.services.research.model_budget import ModelAccountingPolicy
from app.services.research.openai_compatible_provider import (
    OpenAICompatibleProviderConfig,
    OpenAICompatibleResearchProvider,
)
from app.services.research.resolver_factory import resolve_configured_dataset_object_resolver
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.workflow_worker import ResearchProtocolWorker

_DEPLOYMENT_DISABLED = "RESEARCH_GENERATION_DEPLOYMENT_DISABLED"
_CONFIGURATION_INVALID = "RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID"
_SETTLEMENT_LEASE_MARGIN_SECONDS = 30


@dataclass(frozen=True, slots=True)
class GenerationDeployment:
    """Reviewed generation components reusable by a versioned worker graph."""

    datasets: DatasetRegistry
    executor: ResearchGenerationExecutor
    materializer: ResearchGenerationMaterializer


def create_worker() -> ResearchProtocolWorker:
    """Build the reviewed real GENERATE worker only from server ``Settings``.

    The zero-argument signature is intentional: ``worker_process`` resolves
    image-local deployment factories by this callable.  Tests inject explicit
    ``Settings(_env_file=None)`` by replacing this module's ``get_settings``;
    this function itself never opens a dotenv file, database session, quota
    bucket, or provider transport.
    """

    return _create_worker_from_settings(get_settings())


def _create_worker_from_settings(settings: Settings) -> ResearchProtocolWorker:
    """Compose one fail-closed graph from already-loaded server configuration."""

    if (
        not settings.AI_RESEARCH_PROTOCOL_V2_ENABLED
        or not settings.AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED
    ):
        raise RuntimeError(_DEPLOYMENT_DISABLED)
    deployment = build_generation_deployment(settings)
    return ResearchProtocolWorker(
        stage_attempts=ResearchStageAttemptService(generation_materializer=deployment.materializer),
        executors={
            "CLARIFY": DeterministicClarifyExecutor(),
            "GENERATE": deployment.executor,
        },
        workflow_versions=("generation-v1",),
    )


def build_generation_deployment(settings: Settings) -> GenerationDeployment:
    """Build static generation components without touching database or network state.

    Versioned deployment factories call this helper instead of reconstructing
    a second provider, resolver, prompt, quota, and materialization policy.
    Rollout flags remain the responsibility of the outer worker factory.
    """

    try:
        resolver = resolve_configured_dataset_object_resolver(settings)
        if resolver is None:
            raise ValueError("dataset resolver unavailable")
        sampling_params = _configured_json_mapping(
            settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_SAMPLING_PARAMS_JSON
        )
        environment_manifest = _configured_json_mapping(
            settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_ENVIRONMENT_MANIFEST_JSON
        )
        if not environment_manifest:
            raise ValueError("environment manifest unavailable")

        max_output_tokens = _exact_positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_OUTPUT_TOKENS
        )
        reserved_tokens = _exact_positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_RESERVED_TOKENS
        )
        if max_output_tokens > reserved_tokens:
            raise ValueError("output exceeds reserve")
        if type(sampling_params.get("max_tokens")) is not int or (
            sampling_params["max_tokens"] != max_output_tokens
        ):
            raise ValueError("sampling output cap is not pinned")
        _validate_sampling_params(sampling_params)

        api_key = _required_secret(settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_API_KEY)
        provider_config = OpenAICompatibleProviderConfig(
            provider_id=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_PROVIDER_ID),
            endpoint_url=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_ENDPOINT_URL),
            model_id=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_MODEL_ID),
            api_key=api_key,
            timeout_seconds=settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_TIMEOUT_SECONDS,
            max_output_tokens=max_output_tokens,
            max_response_bytes=settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_RESPONSE_BYTES,
            max_request_bytes=settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES,
        )
        quota_lease_seconds = _exact_positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_QUOTA_LEASE_SECONDS
        )
        if quota_lease_seconds < math.ceil(provider_config.timeout_seconds) + (
            _SETTLEMENT_LEASE_MARGIN_SECONDS
        ):
            raise ValueError("quota lease cannot cover provider and settlement")
        accounting_policy = ModelAccountingPolicy.from_mapping(
            _configured_json_mapping(
                settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_JSON
            ),
            expected_hash=_required_text(
                settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_HASH
            ),
        )
        accounting = accounting_policy.snapshot()
        if (
            accounting["provider_id"] != provider_config.provider_id
            or accounting["model_id"] != provider_config.model_id
            or accounting["endpoint_hash"]
            != sha256(provider_config.endpoint_url.encode()).hexdigest()
            or max_output_tokens > accounting["max_output_tokens"]
            or accounting["max_billable_input_tokens"] + max_output_tokens > reserved_tokens
        ):
            raise ValueError("accounting contract does not cover deployment")
        model_alias = _required_text(settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_MODEL_ALIAS)
        gateway = LlmGateway(
            provider=OpenAICompatibleResearchProvider(config=provider_config),
            catalog=ModelCatalog({model_alias: provider_config.model_id}),
            provider_identity=provider_config.provider_id,
            require_model_identity=True,
            accounting_policy=accounting_policy,
            dispatch_timeout_seconds=provider_config.timeout_seconds,
        )
        datasets = DatasetRegistry(object_resolver=resolver)
        executor = ResearchGenerationExecutor(
            gateway=gateway,
            dataset_registry=datasets,
            policy=GenerationExecutorPolicy(
                model_alias=model_alias,
                prompt_template_version=_required_text(
                    settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_PROMPT_TEMPLATE_VERSION
                ),
                prompt_content=_required_text(
                    settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_PROMPT_CONTENT
                ),
                prompt_content_hash=_required_text(
                    settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_PROMPT_CONTENT_HASH
                ),
                sampling_params=sampling_params,
                quota_policy_version=_required_text(
                    settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_QUOTA_POLICY_VERSION
                ),
                reserved_tokens=reserved_tokens,
                quota_lease_seconds=quota_lease_seconds,
            ),
        )
        materializer = ResearchGenerationMaterializer(
            policy=GenerationMaterializationPolicy(
                version=_required_text(
                    settings.AI_RESEARCH_PROTOCOL_V2_GENERATION_MATERIALIZATION_POLICY_VERSION
                ),
                environment_manifest=environment_manifest,
            ),
            dataset_registry=datasets,
        )
        return GenerationDeployment(
            datasets=datasets,
            executor=executor,
            materializer=materializer,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        # Do not echo endpoint URLs, controlled-root locations, prompt text, or
        # credentials through an operator-visible process bootstrap error.
        raise ValueError(_CONFIGURATION_INVALID) from None


def _configured_json_mapping(value: object) -> dict[str, Any]:
    """Parse a bounded server setting as ordinary finite JSON object data."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing JSON configuration")
    try:
        parsed = json.loads(value, parse_constant=_reject_nonstandard_json_constant)
        normalized = normalize_payload(parsed)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("invalid JSON configuration") from None
    if not isinstance(normalized, dict):
        raise ValueError("JSON configuration is not an object")
    return normalized


def _reject_nonstandard_json_constant(value: str) -> None:
    """Make NaN/Infinity an invalid settings value rather than a model input."""

    raise ValueError(f"invalid JSON constant: {value}")


def _required_text(value: object) -> str:
    """Return one static deployment text field without coercing arbitrary values."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing deployment text")
    return value


def _validate_sampling_params(sampling_params: dict[str, Any]) -> None:
    """Reject latent adapter-invalid sampling settings at worker bootstrap."""

    if set(sampling_params) - {"temperature", "top_p", "seed", "max_tokens"}:
        raise ValueError("sampling parameter is not allowlisted")
    for key, ceiling in (("temperature", 2), ("top_p", 1)):
        if key in sampling_params and (
            (value := sampling_params[key]) is None
            or type(value) not in {int, float}
            or not math.isfinite(value)
            or not 0 <= value <= ceiling
        ):
            raise ValueError("sampling parameter is invalid")
    if "seed" in sampling_params and (
        (seed := sampling_params["seed"]) is None
        or type(seed) is not int
        or not -(2**31) <= seed < 2**31
    ):
        raise ValueError("sampling parameter is invalid")


def _required_secret(value: object) -> SecretStr:
    """Require a nonempty non-string secret to avoid an accidental config fallback."""

    if not isinstance(value, SecretStr) or not value.get_secret_value():
        raise ValueError("missing deployment credential")
    return value


def _exact_positive_int(value: object) -> int:
    """Reject bools and implicit string coercion in resource-bound configuration."""

    if type(value) is not int or value <= 0:
        raise ValueError("invalid deployment integer")
    return value
