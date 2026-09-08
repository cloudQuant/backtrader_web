"""Opt-in composition tests for the real protocol-v2 GENERATE worker.

These tests construct only deployment objects from explicit ``Settings``.  They
never execute a worker, query a business database, create quota buckets, or
send a provider request; provider-transport behavior has its own adapter tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services.research.canonical import content_hash


def test_generation_deployment_requires_both_protocol_and_worker_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An importable real factory stays inert until both rollout gates are true."""

    from app.research_deployments import generation

    for flag in (
        "AI_RESEARCH_PROTOCOL_V2_ENABLED",
        "AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED",
    ):
        settings = _settings(tmp_path, **{flag: False})
        monkeypatch.setattr(generation, "get_settings", lambda settings=settings: settings)

        with pytest.raises(RuntimeError, match="^RESEARCH_GENERATION_DEPLOYMENT_DISABLED$"):
            generation.create_worker()


def test_generation_deployment_rejects_incomplete_static_configuration_without_leaking_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A deployed factory cannot silently choose a provider, secret, or resolver."""

    from app.research_deployments import generation

    settings = _settings(
        tmp_path,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_API_KEY=SecretStr(""),
    )
    monkeypatch.setattr(generation, "get_settings", lambda: settings)

    with pytest.raises(
        ValueError, match="^RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID$"
    ) as error:
        generation.create_worker()

    assert "deployment-test-secret" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_generation_deployment_caps_provider_output_by_the_fenced_reservation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The adapter output cap cannot be larger than the executor's quota reserve."""

    from app.research_deployments import generation

    settings = _settings(
        tmp_path,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_OUTPUT_TOKENS=65,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_RESERVED_TOKENS=64,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_SAMPLING_PARAMS_JSON='{"max_tokens":65}',
    )
    monkeypatch.setattr(generation, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="^RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID$"):
        generation.create_worker()


@pytest.mark.parametrize("setting", ["ACCOUNTING_POLICY_JSON", "ACCOUNTING_POLICY_HASH"])
def test_generation_deployment_requires_pinned_accounting_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    from app.research_deployments import generation

    settings = _settings(tmp_path, **{f"AI_RESEARCH_PROTOCOL_V2_GENERATION_{setting}": ""})
    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="^RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID$"):
        generation.create_worker()


def test_generation_deployment_rejects_input_plus_output_above_total_token_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.research_deployments import generation

    settings = _settings(tmp_path, AI_RESEARCH_PROTOCOL_V2_GENERATION_RESERVED_TOKENS=159)
    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="^RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID$"):
        generation.create_worker()


@pytest.mark.parametrize("quota_lease", [1, 60, 89])
def test_generation_deployment_quota_lease_must_cover_http_and_settlement_margin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, quota_lease: int
) -> None:
    from app.research_deployments import generation

    settings = _settings(
        tmp_path, AI_RESEARCH_PROTOCOL_V2_GENERATION_QUOTA_LEASE_SECONDS=quota_lease
    )
    monkeypatch.setattr(generation, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="^RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID$"):
        generation.create_worker()


@pytest.mark.parametrize(
    "sampling_params",
    (
        '{"max_tokens":32,"temperature":null}',
        '{"max_tokens":32,"top_p":null}',
        '{"max_tokens":32,"seed":null}',
    ),
)
def test_generation_deployment_rejects_explicit_null_sampling_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, sampling_params: str
) -> None:
    """Bootstrap must reject the same null values the pinned adapter would reject later."""

    from app.research_deployments import generation

    settings = _settings(
        tmp_path,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_SAMPLING_PARAMS_JSON=sampling_params,
    )
    monkeypatch.setattr(generation, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="^RESEARCH_GENERATION_DEPLOYMENT_CONFIGURATION_INVALID$"):
        generation.create_worker()


def test_generation_deployment_builds_only_the_reviewed_real_composition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The factory injects one fixed adapter, resolver registry, executor, and materializer."""

    from app.research_deployments import generation
    from app.services.research.deterministic_executor import DeterministicClarifyExecutor
    from app.services.research.generation_executor import ResearchGenerationExecutor
    from app.services.research.generation_materialization import ResearchGenerationMaterializer
    from app.services.research.llm_gateway import LlmGateway
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider
    from app.services.research.stage_attempt import ResearchStageAttemptService
    from app.services.research.workflow_worker import ResearchProtocolWorker

    settings = _settings(tmp_path)
    monkeypatch.setattr(generation, "get_settings", lambda: settings)

    worker = generation.create_worker()

    assert isinstance(worker, ResearchProtocolWorker)
    assert worker.has_complete_executor_set is True
    assert worker._tasks.workflow_versions == ("generation-v1",)
    assert set(worker._executors) == {"CLARIFY", "GENERATE"}
    assert isinstance(worker._executors["CLARIFY"], DeterministicClarifyExecutor)
    executor = worker._executors["GENERATE"]
    assert isinstance(executor, ResearchGenerationExecutor)
    assert isinstance(executor._gateway, LlmGateway)
    assert isinstance(executor._gateway._provider, OpenAICompatibleResearchProvider)
    assert executor._gateway._catalog.resolve("trusted-research") == "pinned-model-v1"
    assert isinstance(worker._stage_attempts, ResearchStageAttemptService)
    materializer = worker._stage_attempts._generation_materializer
    assert isinstance(materializer, ResearchGenerationMaterializer)
    assert executor._datasets is materializer._datasets
    assert executor._policy.reserved_tokens == 160
    assert executor._policy.sampling_params["max_tokens"] == 32


def test_generation_deployment_exposes_one_reusable_shared_component_bundle(
    tmp_path: Path,
) -> None:
    """A discovery composition can reuse generation policy without recreating its registry."""

    from app.research_deployments import generation
    from app.services.research.generation_executor import ResearchGenerationExecutor
    from app.services.research.generation_materialization import ResearchGenerationMaterializer

    components = generation.build_generation_deployment(_settings(tmp_path))

    assert isinstance(components.executor, ResearchGenerationExecutor)
    assert isinstance(components.materializer, ResearchGenerationMaterializer)
    assert components.datasets is components.executor._datasets
    assert components.datasets is components.materializer._datasets


def test_generation_deployment_uses_explicit_settings_without_a_dotenv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The composition can be built from explicit server settings without reading a local .env."""

    from app.research_deployments import generation

    settings = _settings(tmp_path)
    assert settings.model_fields_set
    assert "deployment-test-secret" not in repr(settings)
    monkeypatch.setattr(generation, "get_settings", lambda: settings)

    worker = generation.create_worker()

    assert worker.has_complete_executor_set is True


def test_generation_deployment_construction_never_persists_or_dispatches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Startup wires capabilities only; it cannot reserve quota, query DB, or call a provider."""

    from app.db import database
    from app.research_deployments import generation
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider
    from app.services.research.quota import QuotaService

    calls: list[str] = []

    def forbidden_database_access(*args: object, **kwargs: object) -> None:
        calls.append("database")
        raise AssertionError("worker construction must not access the database")

    async def forbidden_provider_dispatch(*args: object, **kwargs: object) -> None:
        calls.append("provider")
        raise AssertionError("worker construction must not dispatch a provider request")

    async def forbidden_quota_reservation(*args: object, **kwargs: object) -> None:
        calls.append("quota")
        raise AssertionError("worker construction must not reserve quota")

    monkeypatch.setattr(database, "async_session_maker", forbidden_database_access)
    monkeypatch.setattr(OpenAICompatibleResearchProvider, "generate", forbidden_provider_dispatch)
    monkeypatch.setattr(QuotaService, "reserve", forbidden_quota_reservation)
    monkeypatch.setattr(generation, "get_settings", lambda: _settings(tmp_path))

    worker = generation.create_worker()

    assert worker.has_complete_executor_set is True
    assert calls == []


def _settings(tmp_path: Path, **changes: object) -> Settings:
    """Build a complete fake-free deployment contract from real temporary roots."""

    object_root = tmp_path / "objects"
    receipt_store = tmp_path / "receipts"
    object_root.mkdir(exist_ok=True)
    receipt_store.mkdir(exist_ok=True)
    prompt = "Return only one reviewed research-generation-v1 JSON object."
    accounting = _accounting_contract()
    values: dict[str, object] = {
        "DEBUG": True,
        "AI_RESEARCH_PROTOCOL_V2_ENABLED": True,
        "AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED": True,
        "AI_RESEARCH_PROTOCOL_V2_DATASET_OBJECT_RESOLVER_TYPE": "filesystem",
        "AI_RESEARCH_PROTOCOL_V2_DATASET_FILESYSTEM_ROOT": str(object_root),
        "AI_RESEARCH_PROTOCOL_V2_DATASET_RECEIPT_STORE": str(receipt_store),
        "AI_RESEARCH_PROTOCOL_V2_DATASET_MAX_BYTES": 1024,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_PROVIDER_ID": "operator-route-v1",
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_ENDPOINT_URL": (
            "https://provider.example/v1/chat/completions"
        ),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_MODEL_ALIAS": "trusted-research",
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_MODEL_ID": "pinned-model-v1",
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_API_KEY": SecretStr("deployment-test-secret"),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_TIMEOUT_SECONDS": 60.0,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_OUTPUT_TOKENS": 32,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_RESPONSE_BYTES": 1024,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES": 1024,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_PROMPT_TEMPLATE_VERSION": "generation-prompt-v1",
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_PROMPT_CONTENT": prompt,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_PROMPT_CONTENT_HASH": content_hash({"prompt": prompt}),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_SAMPLING_PARAMS_JSON": (
            '{"max_tokens":32,"temperature":0.1}'
        ),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_QUOTA_POLICY_VERSION": "generation-quota-v1",
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_RESERVED_TOKENS": 160,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_JSON": json.dumps(accounting),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_ACCOUNTING_POLICY_HASH": content_hash(accounting),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_QUOTA_LEASE_SECONDS": 120,
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_MATERIALIZATION_POLICY_VERSION": (
            "generation-materialization-v1"
        ),
        "AI_RESEARCH_PROTOCOL_V2_GENERATION_ENVIRONMENT_MANIFEST_JSON": (
            '{"image":"trusted-research-test","policy":"fixed"}'
        ),
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def _accounting_contract(**changes: object) -> dict:
    """Synthetic contract for local mechanisms only, not a real provider attestation."""

    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": "model-accounting-v1",
        "version": "synthetic-price-v1",
        "provider_id": "operator-route-v1",
        "model_id": "pinned-model-v1",
        "endpoint_hash": sha256(b"https://provider.example/v1/chat/completions").hexdigest(),
        "max_billable_input_tokens": 128,
        "max_output_tokens": 32,
        "input_microusd_per_million": 1_000_000,
        "output_microusd_per_million": 2_000_000,
        "fixed_microusd": 7,
        "valid_from": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "evidence_hash": "e" * 64,
        "accounting_contract": "ALL_INCLUSIVE_TEXT_CHAT_V1",
        "output_contract": "MAX_TOKENS_ALL_BILLABLE",
        "pricing_contract": "ADMISSION_PRICE_ALL_INCLUSIVE_V1",
    }
    payload.update(changes)
    return payload
