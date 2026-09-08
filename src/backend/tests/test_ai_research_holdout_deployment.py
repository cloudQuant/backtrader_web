"""Static composition tests for the separately deployed holdout worker."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from app.config import Settings


def _settings(tmp_path: Path, **changes: object) -> Settings:
    from tests.test_ai_research_generation_deployment import _settings as generation_settings

    values: dict[str, object] = {
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_ENABLED": True,
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_FACTORY": (
            "app.research_deployments.holdout:create_worker"
        ),
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_POLL_SECONDS": 1.0,
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_ENDPOINT_URL": (
            "https://holdout.example/v1/holdout-executions"
        ),
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_BEARER_TOKEN": SecretStr("deployment-holdout-test-token"),
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_IDENTITY": "holdout-worker-v1",
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_EVALUATOR_IDENTITY": "ai_research_evaluator",
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_EVALUATOR_IMAGE_DIGEST": "sha256:" + "5" * 64,
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_HTTP_TIMEOUT_SECONDS": 60.0,
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_MAX_RESPONSE_BYTES": 1_000_000,
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_LEASE_SECONDS": 180,
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_HEARTBEAT_SECONDS": 30.0,
    }
    values.update(changes)
    return generation_settings(tmp_path, **values)


def test_holdout_deployment_requires_protocol_and_dedicated_worker_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.research_deployments import holdout

    for flag in (
        "AI_RESEARCH_PROTOCOL_V2_ENABLED",
        "AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_ENABLED",
    ):
        settings = _settings(tmp_path, **{flag: False})
        monkeypatch.setattr(holdout, "get_settings", lambda settings=settings: settings)
        with pytest.raises(RuntimeError, match="^RESEARCH_HOLDOUT_DEPLOYMENT_DISABLED$"):
            holdout.create_worker()


@pytest.mark.parametrize(
    "changes",
    (
        {"AI_RESEARCH_PROTOCOL_V2_HOLDOUT_ENDPOINT_URL": ""},
        {"AI_RESEARCH_PROTOCOL_V2_HOLDOUT_BEARER_TOKEN": SecretStr("")},
        {"AI_RESEARCH_PROTOCOL_V2_HOLDOUT_EVALUATOR_IMAGE_DIGEST": "latest"},
        {"AI_RESEARCH_PROTOCOL_V2_HOLDOUT_HEARTBEAT_SECONDS": 180.0},
        {"AI_RESEARCH_PROTOCOL_V2_DATASET_OBJECT_RESOLVER_TYPE": ""},
    ),
)
def test_holdout_deployment_fails_closed_without_leaking_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    changes: dict[str, object],
) -> None:
    from app.research_deployments import holdout

    monkeypatch.setattr(holdout, "get_settings", lambda: _settings(tmp_path, **changes))
    with pytest.raises(
        ValueError,
        match="^RESEARCH_HOLDOUT_DEPLOYMENT_CONFIGURATION_INVALID$",
    ) as error:
        holdout.create_worker()
    assert "deployment-holdout-test-token" not in str(error.value)
    assert "holdout.example" not in str(error.value)
    assert str(tmp_path) not in str(error.value)


def test_holdout_deployment_builds_only_reviewed_components(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.research_deployments import holdout
    from app.services.research.holdout_claim import HoldoutClaimService
    from app.services.research.holdout_execution_journal import HoldoutExecutionJournal
    from app.services.research.holdout_finalize import HoldoutFinalizeService
    from app.services.research.holdout_worker import HoldoutEvaluationWorker
    from app.services.research.http_holdout_executor import HttpSealedHoldoutExecutor

    monkeypatch.setattr(holdout, "get_settings", lambda: _settings(tmp_path))
    worker = holdout.create_worker()

    assert isinstance(worker, HoldoutEvaluationWorker)
    assert isinstance(worker._executor, HttpSealedHoldoutExecutor)
    assert isinstance(worker._claims, HoldoutClaimService)
    assert isinstance(worker._finalize, HoldoutFinalizeService)
    assert isinstance(worker._journal, HoldoutExecutionJournal)
    assert worker._claims._datasets is worker._evidence._datasets
    assert worker._runtime.worker_identity == "holdout-worker-v1"
    assert worker._runtime.evaluator_image_digest == "sha256:" + "5" * 64
    assert "deployment-holdout-test-token" not in repr(worker._executor)
    assert worker._active_lease_tokens == {}


def test_holdout_deployment_construction_has_no_database_or_http_side_effect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.db import database
    from app.research_deployments import holdout
    from app.services.research.http_holdout_executor import HttpSealedHoldoutExecutor

    calls: list[str] = []

    def forbidden_database(*args: object, **kwargs: object) -> None:
        calls.append("database")
        raise AssertionError("construction must not access database")

    async def forbidden_http(*args: object, **kwargs: object) -> None:
        calls.append("http")
        raise AssertionError("construction must not dispatch HTTP")

    monkeypatch.setattr(database, "async_session_maker", forbidden_database)
    monkeypatch.setattr(HttpSealedHoldoutExecutor, "execute", forbidden_http)
    monkeypatch.setattr(holdout, "get_settings", lambda: _settings(tmp_path))

    worker = holdout.create_worker()

    assert isinstance(worker, object)
    assert calls == []


def test_holdout_compose_is_opt_in_nonroot_readonly_and_network_separated() -> None:
    repository = Path(__file__).resolve().parents[3]
    compose_path = repository / "docker" / "compose" / "trusted-research-holdout.yml"
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    service = document["services"]["trusted-research-holdout"]

    assert service["profiles"] == ["trusted-research-holdout"]
    assert service["user"] == "1000:1000"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert set(service["networks"]) == {"holdout-database", "holdout-evaluator-egress"}
    assert document["networks"]["holdout-database"]["internal"] is True
    environment = service["environment"]
    assert environment["AI_RESEARCH_PROTOCOL_V2_HOLDOUT_WORKER_ENABLED"].endswith(":-false}")
    assert "AI_RESEARCH_PROTOCOL_V2_WORKER_ENABLED" not in environment
