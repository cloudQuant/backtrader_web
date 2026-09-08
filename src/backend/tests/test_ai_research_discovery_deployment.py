"""Deployment composition and worker-pipeline proof for discovery-v1.

The factory is intentionally a pure composition root: these tests construct
real policy-bound services, filesystem resolver configuration, SQLite state,
and HTTP adapters, but replace only the two outbound HTTP transports.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings


def test_discovery_deployment_requires_both_protocol_and_worker_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An importable discovery worker remains inert until both rollout gates are true."""

    from app.research_deployments import discovery

    for flag in (
        "AI_RESEARCH_PROTOCOL_V2_ENABLED",
        "AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED",
    ):
        settings = _settings(tmp_path, **{flag: False})
        monkeypatch.setattr(discovery, "get_settings", lambda settings=settings: settings)

        with pytest.raises(RuntimeError, match="^RESEARCH_DISCOVERY_DEPLOYMENT_DISABLED$"):
            discovery.create_worker()


@pytest.mark.parametrize(
    "changes",
    (
        {"AI_RESEARCH_PROTOCOL_V2_DISCOVERY_ENDPOINT_URL": ""},
        {"AI_RESEARCH_PROTOCOL_V2_DISCOVERY_BEARER_TOKEN": SecretStr("")},
        {"AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_NETWORK_MODE": "bridge"},
        {"AI_RESEARCH_PROTOCOL_V2_DISCOVERY_HTTP_TIMEOUT_SECONDS": 64},
        {"AI_RESEARCH_PROTOCOL_V2_DISCOVERY_QUOTA_LEASE_SECONDS": 179},
    ),
)
def test_discovery_deployment_rejects_incomplete_or_unsafe_static_configuration_without_leaks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    """All discovery endpoint, credential, policy, and lease controls fail closed."""

    from app.research_deployments import discovery

    token = "deployment-discovery-test-token"
    settings = _settings(tmp_path, **changes)
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)

    with pytest.raises(
        ValueError, match="^RESEARCH_DISCOVERY_DEPLOYMENT_CONFIGURATION_INVALID$"
    ) as error:
        discovery.create_worker()

    assert token not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_discovery_deployment_builds_one_versioned_worker_with_shared_generation_and_discovery_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One discovery factory can lease old and new graphs without duplicating generation policy."""

    from app.research_deployments import discovery
    from app.services.research.deterministic_executor import DeterministicClarifyExecutor
    from app.services.research.discovery_sandbox import DiscoverySandboxService
    from app.services.research.discovery_stage_executor import DiscoveryStageExecutor
    from app.services.research.discovery_trial_materialization import DiscoveryTrialMaterializer
    from app.services.research.generation_executor import ResearchGenerationExecutor
    from app.services.research.generation_materialization import ResearchGenerationMaterializer
    from app.services.research.http_discovery_sandbox import HttpDiscoverySandboxExecutor
    from app.services.research.stage_attempt import ResearchStageAttemptService
    from app.services.research.workflow_worker import ResearchProtocolWorker

    settings = _settings(tmp_path)
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)

    worker = discovery.create_worker()

    assert isinstance(worker, ResearchProtocolWorker)
    assert worker.has_complete_executor_set is True
    assert worker._tasks.workflow_versions == ("generation-v1", "discovery-v1")
    assert set(worker._executors) == {"CLARIFY", "GENERATE", "VALIDATE_DISCOVERY"}
    assert isinstance(worker._executors["CLARIFY"], DeterministicClarifyExecutor)
    assert isinstance(worker._executors["GENERATE"], ResearchGenerationExecutor)
    assert isinstance(worker._executors["VALIDATE_DISCOVERY"], DiscoveryStageExecutor)
    assert isinstance(worker._stage_attempts, ResearchStageAttemptService)

    generation_executor = worker._executors["GENERATE"]
    generation_materializer = worker._stage_attempts._generation_materializer
    discovery_materializer = worker._stage_attempts._discovery_materializer
    discovery_stage = worker._executors["VALIDATE_DISCOVERY"]
    sandbox = discovery_stage._sandbox

    assert isinstance(generation_materializer, ResearchGenerationMaterializer)
    assert isinstance(discovery_materializer, DiscoveryTrialMaterializer)
    assert isinstance(sandbox, DiscoverySandboxService)
    assert isinstance(sandbox._executor, HttpDiscoverySandboxExecutor)
    assert generation_executor._datasets is generation_materializer._datasets
    assert generation_executor._datasets is discovery_materializer._datasets
    assert generation_executor._datasets is sandbox._datasets
    assert sandbox._runner_identity == "discovery-runner-v1"
    assert sandbox._quota_policy_version == "discovery-quota-v1"
    assert sandbox._quota_lease_seconds == 180
    assert sandbox._policy.network_mode == "none"
    assert "deployment-discovery-test-token" not in repr(sandbox._executor)


def test_discovery_deployment_construction_never_persists_or_dispatches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Bootstrap wires static components only; no database, quota, or HTTP side effect is allowed."""

    from app.db import database
    from app.research_deployments import discovery, generation
    from app.services.research.http_discovery_sandbox import HttpDiscoverySandboxExecutor
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider
    from app.services.research.quota import QuotaService

    calls: list[str] = []

    def forbidden_database_access(*args: object, **kwargs: object) -> None:
        calls.append("database")
        raise AssertionError("worker construction must not access the database")

    async def forbidden_provider_dispatch(*args: object, **kwargs: object) -> None:
        calls.append("provider")
        raise AssertionError("worker construction must not dispatch a provider request")

    async def forbidden_discovery_dispatch(*args: object, **kwargs: object) -> None:
        calls.append("discovery")
        raise AssertionError("worker construction must not dispatch discovery HTTP")

    async def forbidden_quota_reservation(*args: object, **kwargs: object) -> None:
        calls.append("quota")
        raise AssertionError("worker construction must not reserve quota")

    monkeypatch.setattr(database, "async_session_maker", forbidden_database_access)
    monkeypatch.setattr(OpenAICompatibleResearchProvider, "generate", forbidden_provider_dispatch)
    monkeypatch.setattr(HttpDiscoverySandboxExecutor, "run", forbidden_discovery_dispatch)
    monkeypatch.setattr(QuotaService, "reserve", forbidden_quota_reservation)
    monkeypatch.setattr(discovery, "get_settings", lambda: _settings(tmp_path))
    # The reusable builder lives in generation.py; patching the concrete provider
    # method above proves discovery construction does not accidentally invoke it.
    assert generation is not None

    worker = discovery.create_worker()

    assert worker.has_complete_executor_set is True
    assert calls == []


@pytest.mark.asyncio
async def test_configured_discovery_worker_runs_real_three_stage_pipeline_over_two_http_boundaries(
    auth_user,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A discovery-v1 run completes CLARIFY, GENERATE, then discovered trial publication once."""

    from app.db import database
    from app.models.ai_research_v2 import (
        ResearchCapabilityProfile,
        ResearchDiscoveryExecution,
        ResearchQuotaBucket,
        ResearchRun,
        ResearchStageArtifactBinding,
        ResearchStageAttempt,
        ResearchTask,
        ResearchTrial,
    )
    from app.research_deployments import discovery, generation
    from app.services.research.capabilities import CapabilityProfile
    from app.services.research.capability_registry import CapabilityRegistry
    from app.services.research.data_precheck import ResearchDataPrecheckService
    from app.services.research.discovery_execution_contract import DiscoveryExecutionCommand
    from app.services.research.http_discovery_sandbox import HttpDiscoverySandboxExecutor
    from app.services.research.openai_compatible_provider import OpenAICompatibleResearchProvider
    from tests.test_ai_research_generation_executor import _generation_context
    from tests.test_ai_research_generation_http_pipeline import _money_bucket
    from tests.test_ai_research_http_discovery_sandbox import _result_bytes

    context = await _generation_context(auth_user, tmp_path, queued_only=True)
    await _money_bucket(context)
    user_id = context["task"].user_id
    now = datetime.now(timezone.utc)
    profile = CapabilityProfile(
        profile_id="discovery-pipeline-profile",
        version="v1",
        service_identities={"explorer": "generation-worker", "runner": "discovery-runner-v1"},
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="d" * 64,
        verified_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
    )
    await CapabilityRegistry().register(profile)
    prechecks = ResearchDataPrecheckService(dataset_registry=context["datasets"])
    request_json: dict[str, object] = {}
    # The queued fixture's durable task is real; obtain the canonical request from it
    # instead of reproducing browser input for the replacement server precheck.
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        assert task is not None
        request_json = dict(task.request_json)
    precheck = await prechecks.create(
        user_id=user_id,
        hypothesis_version_id=context["run"].hypothesis_version_id,
        dataset_snapshot_id=context["dataset"].id,
        experiment_epoch_id=context["run"].experiment_epoch_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        promotion_policy_version=context["run"].promotion_policy_version,
        request_json=request_json,
    )
    assert precheck.status == "PASS", precheck.details
    async with database.async_session_maker() as session:
        run = await session.get(ResearchRun, context["run"].id)
        assert run is not None
        run.workflow_version = "discovery-v1"
        run.capability_profile_id = profile.profile_id
        run.capability_profile_version = profile.version
        run.capability_evidence_hash = profile.evidence_hash
        run.data_precheck_id = precheck.id
        session.add(
            ResearchQuotaBucket(
                scope_type="user",
                scope_id=user_id,
                policy_version="discovery-quota-v1",
                resource_type="sandbox_seconds",
                window_start=now - timedelta(minutes=1),
                window_end=now + timedelta(hours=1),
                hard_limit=100,
                concurrency_limit=2,
            )
        )
        await session.commit()

    generation_requests: list[httpx.Request] = []
    discovery_requests: list[httpx.Request] = []
    generated_output = json.dumps(
        {
            "schema_version": "research-generation-v1",
            "strategy_code": "class Strategy:\n    def next(self):\n        return None\n",
            "dependency_lock": "backtrader==1.9.78.123\n",
            "params": {"lookback": 20},
        },
        sort_keys=True,
    )

    async def respond_generation(request: httpx.Request) -> httpx.Response:
        generation_requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "discovery-pipeline-generation-1",
                "model": "pinned-model-v1",
                "choices": [{"finish_reason": "stop", "message": {"content": generated_output}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            },
        )

    async def respond_discovery(request: httpx.Request) -> httpx.Response:
        discovery_requests.append(request)
        command = DiscoveryExecutionCommand.from_mapping(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-encoding": "identity"},
            content=_result_bytes(command),
        )

    settings = _settings(
        tmp_path,
        AI_RESEARCH_PROTOCOL_V2_WORKFLOW_VERSION="discovery-v1",
        AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_REQUEST_BYTES=65536,
        AI_RESEARCH_PROTOCOL_V2_GENERATION_MAX_RESPONSE_BYTES=65536,
    )
    real_discovery_executor = HttpDiscoverySandboxExecutor
    monkeypatch.setattr(discovery, "get_settings", lambda: settings)
    monkeypatch.setattr(
        generation,
        "OpenAICompatibleResearchProvider",
        lambda *, config: OpenAICompatibleResearchProvider(
            config=config,
            transport=httpx.MockTransport(respond_generation),
        ),
    )
    monkeypatch.setattr(
        discovery,
        "HttpDiscoverySandboxExecutor",
        lambda *, endpoint, bearer_token, runner_identity, timeout_seconds: real_discovery_executor(
            endpoint=endpoint,
            bearer_token=bearer_token,
            runner_identity=runner_identity,
            timeout_seconds=timeout_seconds,
            transport=httpx.MockTransport(respond_discovery),
        ),
    )

    results = await discovery.create_worker().run_once()

    assert [(result.status, result.error_code) for result in results] == [("SUCCEEDED", None)]
    assert len(generation_requests) == 1
    assert len(discovery_requests) == 1
    assert "controlled://" not in generation_requests[0].content.decode()
    assert "controlled://" not in discovery_requests[0].content.decode()
    async with database.async_session_maker() as session:
        task = await session.get(ResearchTask, context["task"].id)
        run = await session.get(ResearchRun, context["run"].id)
        stages = list(
            await session.scalars(
                select(ResearchStageAttempt)
                .where(ResearchStageAttempt.task_id == context["task"].id)
                .order_by(ResearchStageAttempt.started_at)
            )
        )
        journals = list(
            await session.scalars(
                select(ResearchDiscoveryExecution).where(
                    ResearchDiscoveryExecution.task_id == context["task"].id
                )
            )
        )
        trials = list(
            await session.scalars(
                select(ResearchTrial).where(ResearchTrial.run_id == context["run"].id)
            )
        )
        bindings = list(
            await session.scalars(
                select(ResearchStageArtifactBinding).where(
                    ResearchStageArtifactBinding.task_id == context["task"].id
                )
            )
        )
        capability = await session.scalar(
            select(ResearchCapabilityProfile).where(
                ResearchCapabilityProfile.profile_id == profile.profile_id,
                ResearchCapabilityProfile.version == profile.version,
            )
        )

    assert task is not None and task.status == "SUCCEEDED"
    assert run is not None and run.status == "SUCCEEDED"
    assert run.workflow_version == "discovery-v1"
    assert [(stage.stage, stage.status) for stage in stages] == [
        ("CLARIFY", "SUCCEEDED"),
        ("GENERATE", "SUCCEEDED"),
        ("VALIDATE_DISCOVERY", "SUCCEEDED"),
    ]
    assert len(journals) == len(trials) == 1
    assert journals[0].trial_id == trials[0].id
    assert trials[0].status == "SUCCEEDED"
    assert any(binding.stage_attempt_id == stages[-1].id for binding in bindings)
    assert capability is not None
    assert await discovery.create_worker().run_once() == []
    assert len(generation_requests) == len(discovery_requests) == 1


def _settings(tmp_path: Path, **changes: object) -> Settings:
    """Combine the reviewed generation fixture with a complete discovery policy."""

    from tests.test_ai_research_generation_deployment import _settings as generation_settings

    values: dict[str, object] = {
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_ENDPOINT_URL": (
            "https://runner.example/v1/discovery-executions"
        ),
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_BEARER_TOKEN": SecretStr(
            "deployment-discovery-test-token"
        ),
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_RUNNER_IDENTITY": "discovery-runner-v1",
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_HTTP_TIMEOUT_SECONDS": 65.0,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_POLICY_VERSION": "discovery-policy-v1",
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_IMAGE_DIGEST": "sha256:" + "d" * 64,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_NETWORK_MODE": "none",
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_INPUT_READ_ONLY": True,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_OUTPUT_PATH": "/sandbox/output",
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_CPU_LIMIT": 1,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_MEMORY_LIMIT_MB": 256,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_PID_LIMIT": 16,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_WALL_TIMEOUT_SECONDS": 60,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_OUTPUT_LIMIT_BYTES": 1_000_000,
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_QUOTA_POLICY_VERSION": "discovery-quota-v1",
        "AI_RESEARCH_PROTOCOL_V2_DISCOVERY_QUOTA_LEASE_SECONDS": 180,
    }
    values.update(changes)
    return generation_settings(tmp_path, **values)
