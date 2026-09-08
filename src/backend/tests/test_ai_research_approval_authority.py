from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.models.ai_research_v2 import ResearchHumanDecision
from app.models.permission import ROLE_PERMISSIONS, Permission, Role
from app.services.research.approval import ApprovalService
from app.services.research.approval_authority import (
    ApprovalPolicyCatalog,
    resolve_server_approval_policy,
    server_approval_capabilities,
)
from app.services.research.capabilities import CapabilityProfile
from app.services.research.capability_registry import CapabilityRegistry


@pytest.mark.parametrize("method_name", ["request_approval", "decide", "approval_context"])
def test_approval_business_methods_do_not_accept_client_authority_fields(
    method_name: str,
) -> None:
    parameters = inspect.signature(getattr(ApprovalService, method_name)).parameters

    assert "authenticated_actor_id" in parameters
    assert {"actor_id", "policy", "domain_permissions", "mode", "now"}.isdisjoint(parameters)


@pytest.mark.parametrize("mode", ["single_actor", "multi_actor"])
def test_server_approval_capability_material_is_complete_and_hash_bound(mode: str) -> None:
    capabilities = server_approval_capabilities(mode)
    policy = resolve_server_approval_policy(capabilities["policy_version"])

    assert capabilities == {
        "mode": mode,
        "policy_version": policy.version,
        "policy_material_hash": policy.material_hash,
        "permissions": ["research:approve"],
    }
    assert policy.mode == mode
    assert policy.required_permission == "research:approve"
    assert "promotion-v1" in policy.promotion_policy_versions


def test_policy_catalog_rejects_unknown_empty_permissions_and_same_version_drift() -> None:
    capabilities = server_approval_capabilities("multi_actor")
    catalog = ApprovalPolicyCatalog()

    with pytest.raises(ValueError, match="^APPROVAL_POLICY_UNSUPPORTED$"):
        catalog.resolve("not-a-policy", capabilities)
    with pytest.raises(ValueError, match="^APPROVAL_CAPABILITY_PROFILE_INVALID$"):
        catalog.resolve(capabilities["policy_version"], {**capabilities, "permissions": []})
    with pytest.raises(ValueError, match="^APPROVAL_POLICY_MATERIAL_MISMATCH$"):
        catalog.resolve(
            capabilities["policy_version"],
            {**capabilities, "policy_material_hash": "0" * 64},
        )


def test_no_default_role_implies_run_scoped_research_approval() -> None:
    assert all(
        Permission.APPROVE_RESEARCH not in permissions for permissions in ROLE_PERMISSIONS.values()
    )


def test_grant_management_permission_requires_the_dedicated_explicit_role() -> None:
    assert Permission.MANAGE_APPROVAL_GRANTS not in (
        ROLE_PERMISSIONS[Role.ADMIN]
        + ROLE_PERMISSIONS[Role.PREMIUM]
        + ROLE_PERMISSIONS[Role.USER]
        + ROLE_PERMISSIONS[Role.GUEST]
    )
    assert ROLE_PERMISSIONS[Role.RESEARCH_APPROVAL_ADMIN] == [Permission.MANAGE_APPROVAL_GRANTS]


def test_one_human_decision_is_allowed_per_exact_approval_request() -> None:
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in ResearchHumanDecision.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("approval_request_id",) in unique_columns


@pytest.mark.asyncio
async def test_capability_registry_persists_server_approval_material() -> None:
    now = datetime.now(timezone.utc)
    profile = CapabilityProfile(
        profile_id="approval-authority-profile",
        version="v1",
        service_identities={"explorer": "explorer", "evaluator": "evaluator"},
        queue_isolation=True,
        storage_isolation=True,
        network_isolation=True,
        sandbox_runner=True,
        approval_mode="multi_actor",
        evidence_hash="a" * 64,
        verified_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        stage_image_digests={"evaluator": "sha256:" + "b" * 64},
    )

    stored = await CapabilityRegistry().register(profile)

    assert stored.approval_capabilities == server_approval_capabilities("multi_actor")
