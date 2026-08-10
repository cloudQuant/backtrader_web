"""Provider network-policy and protocol contracts."""

import pytest

from app.services.asset_research.providers.base import NetworkPolicy


def test_network_policy_rejects_empty_allowed_hosts() -> None:
    with pytest.raises(ValueError, match="PROVIDER_ALLOWED_HOSTS_EMPTY"):
        NetworkPolicy(allowed_hosts=()).validate()


def test_network_policy_enforces_timeout_order() -> None:
    policy = NetworkPolicy(
        allowed_hosts=("api.example.com",),
        connect_timeout_seconds=10,
        read_timeout_seconds=5,
        total_timeout_seconds=30,
    )

    with pytest.raises(ValueError, match="PROVIDER_TIMEOUT_ORDER_INVALID"):
        policy.validate()


def test_network_policy_accepts_valid_defaults() -> None:
    policy = NetworkPolicy(allowed_hosts=("api.example.com",))

    policy.validate()

    assert policy.max_retries == 2

