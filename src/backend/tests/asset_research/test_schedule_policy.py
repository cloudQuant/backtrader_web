"""Calendar-cutoff contracts for the six single-asset shadow schedules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.asset_research.schedule_policy import (
    AssetSchedulePolicyError,
    latest_schedule_fire,
    resolve_schedule_cutoff,
    validate_schedule_contract,
)


@pytest.mark.parametrize(
    ("asset_type", "policy", "fire_at", "expected_cutoff"),
    [
        (
            "bond",
            "bond-cn-after-close-v1",
            datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc),
        ),
        (
            "fund",
            "fund-cn-nav-after-close-v1",
            datetime(2026, 8, 3, 15, 30, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 15, 15, tzinfo=timezone.utc),
        ),
        (
            "futures",
            "futures-complete-session-v1",
            datetime(2026, 8, 3, 11, 10, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc),
        ),
        (
            "fx",
            "fx-ny-close-v1",
            datetime(2026, 7, 1, 21, 10, tzinfo=timezone.utc),
            datetime(2026, 7, 1, 21, 0, tzinfo=timezone.utc),
        ),
        (
            "fx",
            "fx-ny-close-v1",
            datetime(2026, 1, 5, 22, 10, tzinfo=timezone.utc),
            datetime(2026, 1, 5, 22, 0, tzinfo=timezone.utc),
        ),
        (
            "crypto",
            "crypto-utc-daily-v1",
            datetime(2026, 8, 3, 0, 10, tzinfo=timezone.utc),
            datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc),
        ),
    ],
)
def test_asset_schedule_policy_freezes_the_correct_completed_market_cutoff(
    asset_type: str,
    policy: str,
    fire_at: datetime,
    expected_cutoff: datetime,
) -> None:
    """DST and local close calculations must never use the future bar."""
    assert resolve_schedule_cutoff(asset_type, policy, fire_at) == expected_cutoff


def test_latest_schedule_fire_uses_the_last_policy_slot_without_scanning_history() -> None:
    assert latest_schedule_fire(
        cutoff_policy="futures-complete-session-v1",
        at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
    ) == datetime(2026, 8, 7, 11, 10, tzinfo=timezone.utc)


def test_schedule_contract_rejects_a_cross_asset_or_wrong_timezone_policy() -> None:
    """A schedule cannot claim an FX cutoff while running as a futures job."""
    with pytest.raises(AssetSchedulePolicyError, match="SCHEDULE_POLICY_ASSET_MISMATCH"):
        validate_schedule_contract(
            asset_type="futures",
            cutoff_policy="fx-ny-close-v1",
            cron_expression="10 17 * * 1-5",
            timezone_name="America/New_York",
        )

    with pytest.raises(AssetSchedulePolicyError, match="SCHEDULE_TIMEZONE_MISMATCH"):
        validate_schedule_contract(
            asset_type="crypto",
            cutoff_policy="crypto-utc-daily-v1",
            cron_expression="10 0 * * *",
            timezone_name="Asia/Shanghai",
        )
