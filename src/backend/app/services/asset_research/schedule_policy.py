"""Versioned calendar-cutoff rules for single-asset shadow schedules.

The scheduler is intentionally driven by explicit, reviewable policies rather
than a generic ``19:00`` timestamp.  A rule only identifies a completed market
window; exchange and NAV calendars remain data-source facts and may still
reject a non-trading-day snapshot at the quality gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.cron import CronTrigger

from app.services.asset_research.types import AssetResearchAssetType


class AssetSchedulePolicyError(ValueError):
    """Stable schedule configuration or cutoff error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class AssetSchedulePolicy:
    """A versioned, asset-specific fire and point-in-time cutoff contract."""

    policy_id: str
    asset_type: AssetResearchAssetType
    timezone_name: str
    cron_expression: str
    cutoff_time: time


_POLICIES: tuple[AssetSchedulePolicy, ...] = (
    AssetSchedulePolicy(
        "bond-cn-after-close-v1", "bond", "Asia/Shanghai", "10 19 * * 1-5", time(19, 0)
    ),
    AssetSchedulePolicy(
        "bond-us-after-close-v1", "bond", "America/New_York", "30 18 * * 1-5", time(18, 15)
    ),
    AssetSchedulePolicy(
        "fund-cn-etf-after-close-v1", "fund", "Asia/Shanghai", "10 19 * * 1-5", time(19, 0)
    ),
    AssetSchedulePolicy(
        "fund-cn-nav-after-close-v1", "fund", "Asia/Shanghai", "30 23 * * 1-5", time(23, 15)
    ),
    AssetSchedulePolicy(
        "fund-cn-nav-catchup-v1", "fund", "Asia/Shanghai", "30 8 * * 1-5", time(8, 15)
    ),
    AssetSchedulePolicy(
        "fund-us-etf-after-close-v1", "fund", "America/New_York", "30 18 * * 1-5", time(18, 15)
    ),
    AssetSchedulePolicy(
        "futures-complete-session-v1", "futures", "Asia/Shanghai", "10 19 * * 1-5", time(19, 0)
    ),
    AssetSchedulePolicy(
        "option-cn-exchange-close-v1", "option", "Asia/Shanghai", "10 15 * * 1-5", time(15, 0)
    ),
    AssetSchedulePolicy("fx-ny-close-v1", "fx", "America/New_York", "10 17 * * 1-5", time(17, 0)),
    AssetSchedulePolicy("crypto-utc-daily-v1", "crypto", "UTC", "10 0 * * *", time(0, 0)),
)
_POLICY_BY_ID = {policy.policy_id: policy for policy in _POLICIES}


def get_schedule_policy(cutoff_policy: str) -> AssetSchedulePolicy:
    """Return an explicitly supported policy or a stable API-safe error."""
    policy = _POLICY_BY_ID.get(cutoff_policy)
    if policy is None:
        raise AssetSchedulePolicyError("SCHEDULE_POLICY_UNKNOWN")
    return policy


def validate_schedule_contract(
    *,
    asset_type: AssetResearchAssetType,
    cutoff_policy: str,
    cron_expression: str,
    timezone_name: str,
) -> AssetSchedulePolicy:
    """Validate the immutable schedule contract before storing it.

    User-selectable cadence is intentionally not accepted here: a schedule
    that declares a completed New York FX session must actually run after that
    session, and a crypto daily cohort must remain UTC-based.  Interactive
    analysis is available through the task API instead of weakening this
    reproducibility boundary.
    """
    policy = get_schedule_policy(cutoff_policy)
    if policy.asset_type != asset_type:
        raise AssetSchedulePolicyError("SCHEDULE_POLICY_ASSET_MISMATCH")
    if policy.timezone_name != timezone_name:
        raise AssetSchedulePolicyError("SCHEDULE_TIMEZONE_MISMATCH")
    if _normalize_cron(cron_expression) != policy.cron_expression:
        raise AssetSchedulePolicyError("SCHEDULE_CRON_MISMATCH")
    _zoneinfo(timezone_name)
    return policy


def resolve_schedule_cutoff(
    asset_type: str,
    cutoff_policy: str,
    scheduled_fire_at: datetime,
) -> datetime:
    """Calculate a UTC cutoff that is never later than the trigger instant.

    If a manual invocation happens before today's scheduled close, it replays
    the prior cutoff instead of reading a bar that has not completed yet.
    Retry flows persist and reuse the original cutoff rather than calling this
    function again.
    """
    if scheduled_fire_at.tzinfo is None:
        raise AssetSchedulePolicyError("SCHEDULE_TIME_INVALID")
    policy = get_schedule_policy(cutoff_policy)
    if policy.asset_type != asset_type:
        raise AssetSchedulePolicyError("SCHEDULE_POLICY_ASSET_MISMATCH")
    local_zone = _zoneinfo(policy.timezone_name)
    local_fire_at = scheduled_fire_at.astimezone(local_zone)
    local_cutoff = datetime.combine(local_fire_at.date(), policy.cutoff_time, tzinfo=local_zone)
    if local_cutoff > local_fire_at:
        local_cutoff -= timedelta(days=1)
    return local_cutoff.astimezone(timezone.utc)


def next_schedule_fire(
    *,
    cutoff_policy: str,
    after: datetime,
) -> datetime:
    """Return the next UTC trigger after ``after`` using the frozen cron rule."""
    if after.tzinfo is None:
        raise AssetSchedulePolicyError("SCHEDULE_TIME_INVALID")
    policy = get_schedule_policy(cutoff_policy)
    timezone_value = _zoneinfo(policy.timezone_name)
    trigger = CronTrigger.from_crontab(policy.cron_expression, timezone=timezone_value)
    # CronTrigger treats ``now`` as inclusive.  The schedule contract needs a
    # strict successor: otherwise a SKIP misfire at an exact trigger instant
    # would write the same due time back and be claimed forever.
    next_fire = trigger.get_next_fire_time(
        None,
        after.astimezone(timezone_value) + timedelta(microseconds=1),
    )
    if next_fire is None:
        raise AssetSchedulePolicyError("SCHEDULE_NEXT_FIRE_UNAVAILABLE")
    return next_fire.astimezone(timezone.utc)


def latest_schedule_fire(
    *,
    cutoff_policy: str,
    at: datetime,
) -> datetime:
    """Return the most recent configured fire at or before ``at`` in UTC.

    All approved v1 policies are at most daily.  A bounded eight-day search is
    therefore sufficient to cross a weekend without turning a long outage
    into an unbounded cron scan.  The policy registry is the authority for
    that bound; adding a less-frequent policy must extend this helper and its
    tests deliberately.
    """
    if at.tzinfo is None:
        raise AssetSchedulePolicyError("SCHEDULE_TIME_INVALID")
    policy = get_schedule_policy(cutoff_policy)
    timezone_value = _zoneinfo(policy.timezone_name)
    local_at = at.astimezone(timezone_value)
    trigger = CronTrigger.from_crontab(policy.cron_expression, timezone=timezone_value)
    candidate = trigger.get_next_fire_time(None, local_at - timedelta(days=8))
    latest: datetime | None = None
    for _ in range(16):
        if candidate is None or candidate > local_at:
            break
        latest = candidate
        candidate = trigger.get_next_fire_time(candidate, candidate)
    if latest is None:
        raise AssetSchedulePolicyError("SCHEDULE_LATEST_FIRE_UNAVAILABLE")
    return latest.astimezone(timezone.utc)


def supported_schedule_policies() -> tuple[AssetSchedulePolicy, ...]:
    """Expose immutable policy metadata to configuration/admin surfaces."""
    return _POLICIES


def _normalize_cron(value: str) -> str:
    return " ".join(value.split())


def _zoneinfo(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise AssetSchedulePolicyError("SCHEDULE_TIMEZONE_INVALID") from exc
