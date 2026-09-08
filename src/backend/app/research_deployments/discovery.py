"""Opt-in composition root for the versioned protocol-v2 discovery worker.

The factory combines the already-reviewed GENERATE deployment with a pinned
remote discovery runner.  It is intentionally a static bootstrap only: no
database session, quota reservation, HTTP dispatch, Docker client, or browser
input is consulted while this module constructs a worker.
"""

from __future__ import annotations

import math

from pydantic import SecretStr

from app.config import Settings, get_settings
from app.research_deployments.generation import build_generation_deployment
from app.services.research.deterministic_executor import DeterministicClarifyExecutor
from app.services.research.discovery_sandbox import DiscoverySandboxService
from app.services.research.discovery_stage_executor import DiscoveryStageExecutor
from app.services.research.discovery_trial_materialization import DiscoveryTrialMaterializer
from app.services.research.http_discovery_sandbox import HttpDiscoverySandboxExecutor
from app.services.research.sandbox_runner import SandboxPolicy, _validate_policy
from app.services.research.stage_attempt import ResearchStageAttemptService
from app.services.research.workflow_worker import ResearchProtocolWorker

_DEPLOYMENT_DISABLED = "RESEARCH_DISCOVERY_DEPLOYMENT_DISABLED"
_CONFIGURATION_INVALID = "RESEARCH_DISCOVERY_DEPLOYMENT_CONFIGURATION_INVALID"
_WORKFLOW_VERSIONS = ("generation-v1", "discovery-v1")
_HTTP_TIMEOUT_MINIMUM_MARGIN_SECONDS = 5
_HTTP_TIMEOUT_MAXIMUM_MARGIN_SECONDS = 60
_QUOTA_LEASE_MARGIN_SECONDS = 120


def create_worker() -> ResearchProtocolWorker:
    """Build the reviewed versioned worker exclusively from server ``Settings``.

    The zero-argument callable is resolved by the separately deployed worker
    process.  Its construction does not load dotenv, access business data, or
    make a network request; deployment configuration is already loaded by
    ``get_settings`` before this factory is invoked.
    """

    return _create_worker_from_settings(get_settings())


def _create_worker_from_settings(settings: Settings) -> ResearchProtocolWorker:
    """Compose both persistent graph versions and the remote discovery boundary."""

    if (
        not settings.AI_RESEARCH_PROTOCOL_V2_ENABLED
        or not settings.AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED
    ):
        raise RuntimeError(_DEPLOYMENT_DISABLED)
    try:
        generation = build_generation_deployment(settings)
        policy = _sandbox_policy_from_settings(settings)
        _validate_policy(policy)
        http_timeout_seconds = _finite_positive_timeout(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_HTTP_TIMEOUT_SECONDS
        )
        if not (
            policy.wall_timeout_seconds + _HTTP_TIMEOUT_MINIMUM_MARGIN_SECONDS
            <= http_timeout_seconds
            <= policy.wall_timeout_seconds + _HTTP_TIMEOUT_MAXIMUM_MARGIN_SECONDS
        ):
            raise ValueError("HTTP timeout does not cover discovery policy")
        quota_lease_seconds = _positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_QUOTA_LEASE_SECONDS
        )
        if quota_lease_seconds < policy.wall_timeout_seconds + _QUOTA_LEASE_MARGIN_SECONDS:
            raise ValueError("quota lease does not cover discovery policy")
        runner_identity = _required_text(settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_RUNNER_IDENTITY)
        remote_executor = HttpDiscoverySandboxExecutor(
            endpoint=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_ENDPOINT_URL),
            bearer_token=_required_secret_text(
                settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_BEARER_TOKEN
            ),
            runner_identity=runner_identity,
            timeout_seconds=http_timeout_seconds,
        )
        sandbox_service = DiscoverySandboxService(
            executor=remote_executor,
            dataset_registry=generation.datasets,
            policy=policy,
            runner_identity=runner_identity,
            quota_policy_version=_required_text(
                settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_QUOTA_POLICY_VERSION
            ),
            quota_lease_seconds=quota_lease_seconds,
        )
        return ResearchProtocolWorker(
            stage_attempts=ResearchStageAttemptService(
                generation_materializer=generation.materializer,
                discovery_materializer=DiscoveryTrialMaterializer(
                    dataset_registry=generation.datasets
                ),
            ),
            executors={
                "CLARIFY": DeterministicClarifyExecutor(),
                "GENERATE": generation.executor,
                "VALIDATE_DISCOVERY": DiscoveryStageExecutor(sandbox_service=sandbox_service),
            },
            workflow_versions=_WORKFLOW_VERSIONS,
        )
    except (TypeError, ValueError):
        # Never include endpoint, storage root, prompt, policy internals, or a
        # credential in a process bootstrap error visible to an operator.
        raise ValueError(_CONFIGURATION_INVALID) from None


def _sandbox_policy_from_settings(settings: Settings) -> SandboxPolicy:
    """Copy every sandbox control from explicit server configuration without coercion."""

    return SandboxPolicy(
        version=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_POLICY_VERSION),
        image_digest=_required_text(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_IMAGE_DIGEST
        ),
        network_mode=_required_text(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_NETWORK_MODE
        ),
        input_read_only=settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_INPUT_READ_ONLY,
        output_path=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_OUTPUT_PATH),
        cpu_limit=_positive_int(settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_CPU_LIMIT),
        memory_limit_mb=_positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_MEMORY_LIMIT_MB
        ),
        pid_limit=_positive_int(settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_PID_LIMIT),
        wall_timeout_seconds=_positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_WALL_TIMEOUT_SECONDS
        ),
        output_limit_bytes=_positive_int(
            settings.AI_RESEARCH_PROTOCOL_V2_DISCOVERY_SANDBOX_OUTPUT_LIMIT_BYTES
        ),
    )


def _required_text(value: object) -> str:
    """Require static deployment text without silently coercing caller-owned values."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing deployment text")
    return value


def _required_secret_text(value: object) -> str:
    """Extract a nonempty deployment secret only at the HTTP composition boundary."""

    if not isinstance(value, SecretStr):
        raise ValueError("missing deployment secret")
    secret = value.get_secret_value()
    if not isinstance(secret, str) or not secret:
        raise ValueError("missing deployment secret")
    return secret


def _positive_int(value: object) -> int:
    """Reject bools and implicit casts for resource and lease limits."""

    if type(value) is not int or value <= 0:
        raise ValueError("invalid deployment integer")
    return value


def _finite_positive_timeout(value: object) -> float:
    """Reject non-finite values before the HTTP adapter receives a deadline."""

    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError("invalid deployment timeout")
    return float(value)
