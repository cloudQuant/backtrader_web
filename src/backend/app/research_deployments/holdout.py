"""Opt-in composition root for the independent sealed-holdout worker.

The factory consumes only deployment settings.  It does not query the research
database or contact the evaluator while constructing the process graph.
"""

from __future__ import annotations

import math

from pydantic import SecretStr

from app.config import Settings, get_settings
from app.services.research.dataset_registry import DatasetRegistry
from app.services.research.evidence_package import EvidencePackageService
from app.services.research.holdout_claim import (
    HoldoutClaimService,
    HoldoutEvaluatorRuntimeIdentity,
)
from app.services.research.holdout_execution_journal import HoldoutExecutionJournal
from app.services.research.holdout_finalize import HoldoutFinalizeService
from app.services.research.holdout_worker import HoldoutEvaluationWorker
from app.services.research.http_holdout_executor import HttpSealedHoldoutExecutor
from app.services.research.resolver_factory import resolve_configured_dataset_object_resolver

_DEPLOYMENT_DISABLED = "RESEARCH_HOLDOUT_DEPLOYMENT_DISABLED"
_CONFIGURATION_INVALID = "RESEARCH_HOLDOUT_DEPLOYMENT_CONFIGURATION_INVALID"


def create_worker() -> HoldoutEvaluationWorker:
    """Create the reviewed worker from already-loaded server configuration."""

    return _create_worker_from_settings(get_settings())


def _create_worker_from_settings(settings: Settings) -> HoldoutEvaluationWorker:
    if (
        not settings.AI_RESEARCH_PROTOCOL_V2_ENABLED
        or not settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_ENABLED
    ):
        raise RuntimeError(_DEPLOYMENT_DISABLED)
    try:
        resolver = resolve_configured_dataset_object_resolver(settings)
        if resolver is None:
            raise ValueError("dataset resolver unavailable")
        lease_seconds = _positive_int(settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_LEASE_SECONDS)
        heartbeat_seconds = _finite_positive(
            settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_HEARTBEAT_SECONDS
        )
        if heartbeat_seconds >= lease_seconds:
            raise ValueError("heartbeat does not fit lease")
        datasets = DatasetRegistry(object_resolver=resolver)
        runtime = HoldoutEvaluatorRuntimeIdentity(
            worker_identity=_required_identity(
                settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_IDENTITY
            ),
            evaluator_identity=_required_identity(
                settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_EVALUATOR_IDENTITY
            ),
            evaluator_image_digest=_required_image_digest(
                settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_EVALUATOR_IMAGE_DIGEST
            ),
        )
        executor = HttpSealedHoldoutExecutor(
            endpoint=_required_text(settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_ENDPOINT_URL),
            bearer_token=_required_secret(settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_BEARER_TOKEN),
            evaluator_identity=runtime.evaluator_identity,
            evaluator_image_digest=runtime.evaluator_image_digest,
            timeout_seconds=_finite_positive(
                settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_HTTP_TIMEOUT_SECONDS
            ),
            max_response_bytes=_positive_int(
                settings.AI_RESEARCH_PROTOCOL_V2_HOLDOUT_MAX_RESPONSE_BYTES
            ),
        )
        return HoldoutEvaluationWorker(
            executor=executor,
            runtime=runtime,
            claim_service=HoldoutClaimService(
                dataset_registry=datasets,
                lease_seconds=lease_seconds,
            ),
            finalize_service=HoldoutFinalizeService(),
            evidence_service=EvidencePackageService(dataset_registry=datasets),
            journal=HoldoutExecutionJournal(),
            heartbeat_interval_seconds=heartbeat_seconds,
        )
    except (AttributeError, TypeError, ValueError):
        # Endpoint, credential, local resolver roots, and evaluator details must
        # never be reflected into an operator-visible startup error.
        raise ValueError(_CONFIGURATION_INVALID) from None


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing deployment text")
    return value


def _required_identity(value: object) -> str:
    text = _required_text(value)
    if (
        text != text.strip()
        or len(text.encode("utf-8")) > 512
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
        or "://" in text
        or "/" in text
        or "\\" in text
    ):
        raise ValueError("invalid deployment identity")
    return text


def _required_image_digest(value: object) -> str:
    text = _required_identity(value)
    if (
        not text.startswith("sha256:")
        or len(text) != 71
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise ValueError("invalid evaluator image")
    return text


def _required_secret(value: object) -> str:
    if not isinstance(value, SecretStr):
        raise ValueError("missing credential")
    secret = value.get_secret_value()
    if (
        not isinstance(secret, str)
        or not secret
        or any(not 32 < ord(character) < 127 for character in secret)
    ):
        raise ValueError("missing credential")
    return secret


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("invalid deployment integer")
    return value


def _finite_positive(value: object) -> float:
    if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
        raise ValueError("invalid deployment timeout")
    return float(value)
