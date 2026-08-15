"""Frozen, source-backed horizon resolution for multi-asset research.

The result loop must not infer exchange, NAV or FX sessions from weekdays.  A
prediction therefore freezes the relevant future session closes supplied by an
authorized source.  Calendar-day products (currently crypto) are the only
exception because their horizon is explicitly continuous UTC time.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.schemas.asset_research import HorizonSpec, RawAssetSnapshot


@dataclass(frozen=True, slots=True)
class HorizonMaturity:
    """A resolved maturity or an explicit reason why it cannot be resolved."""

    maturity_at: datetime | None
    maturity_reason: str | None
    reason_codes: list[str]
    metrics: dict[str, Any]


def resolve_horizon_maturity(
    *,
    snapshot: RawAssetSnapshot,
    horizon_spec: HorizonSpec,
    as_of: datetime,
) -> HorizonMaturity:
    """Resolve a frozen horizon without a weekday or current-calendar fallback.

    Session products require ``raw_fields.calendar`` with the exact
    ``calendar_id`` and a sequence of future session close timestamps.  A
    date-only session is supported conservatively as the end of that UTC date;
    providers should prefer an exact ``close_at`` timestamp.  Insufficient
    source calendar coverage leaves the outcome pending and unclaimable rather
    than manufacturing a maturity date.
    """
    cutoff = _as_utc(as_of)
    if horizon_spec.unit == "CALENDAR_DAY":
        return HorizonMaturity(
            maturity_at=cutoff + timedelta(days=horizon_spec.count),
            maturity_reason="HORIZON_REACHED",
            reason_codes=[],
            metrics={
                "calendar_id": horizon_spec.calendar_id,
                "calendar_source": "UTC_CONTINUOUS",
                "horizon_unit": horizon_spec.unit,
            },
        )
    if horizon_spec.unit == "CALENDAR_HOUR":
        return HorizonMaturity(
            maturity_at=cutoff + timedelta(hours=horizon_spec.count),
            maturity_reason="HORIZON_REACHED",
            reason_codes=[],
            metrics={
                "calendar_id": horizon_spec.calendar_id,
                "calendar_source": "UTC_CONTINUOUS",
                "horizon_unit": horizon_spec.unit,
            },
        )

    raw_calendar = snapshot.raw_fields.get("calendar")
    if not isinstance(raw_calendar, Mapping):
        return _unavailable(horizon_spec, reason="CALENDAR_PAYLOAD_MISSING")
    actual_calendar_id = raw_calendar.get("calendar_id")
    if str(actual_calendar_id or "") != horizon_spec.calendar_id:
        return _unavailable(
            horizon_spec,
            reason="CALENDAR_ID_MISMATCH",
            actual_calendar_id=str(actual_calendar_id or "") or None,
        )
    raw_sessions = raw_calendar.get("sessions")
    if not isinstance(raw_sessions, Sequence) or isinstance(raw_sessions, (str, bytes)):
        return _unavailable(horizon_spec, reason="CALENDAR_SESSIONS_MISSING")
    sessions = sorted(
        {parsed for item in raw_sessions if (parsed := _session_close(item)) is not None}
    )
    future_sessions = [session for session in sessions if session > cutoff]
    if len(future_sessions) < horizon_spec.count:
        return _unavailable(
            horizon_spec,
            reason="CALENDAR_COVERAGE_INSUFFICIENT",
            available_sessions=len(future_sessions),
        )
    return HorizonMaturity(
        maturity_at=future_sessions[horizon_spec.count - 1],
        maturity_reason="HORIZON_REACHED",
        reason_codes=[],
        metrics={
            "calendar_id": horizon_spec.calendar_id,
            "calendar_source": "FROZEN_SOURCE",
            "horizon_unit": horizon_spec.unit,
            "session_count": horizon_spec.count,
        },
    )


def _unavailable(
    horizon_spec: HorizonSpec,
    *,
    reason: str,
    actual_calendar_id: str | None = None,
    available_sessions: int | None = None,
) -> HorizonMaturity:
    metrics: dict[str, Any] = {
        "calendar_id": horizon_spec.calendar_id,
        "calendar_resolution": reason,
        "horizon_unit": horizon_spec.unit,
        "required_sessions": horizon_spec.count,
    }
    if actual_calendar_id is not None:
        metrics["actual_calendar_id"] = actual_calendar_id
    if available_sessions is not None:
        metrics["available_sessions"] = available_sessions
    return HorizonMaturity(
        maturity_at=None,
        maturity_reason=None,
        reason_codes=["COMMON.CALENDAR_UNAVAILABLE"],
        metrics=metrics,
    )


def _session_close(value: object) -> datetime | None:
    if isinstance(value, Mapping):
        for key in ("close_at", "session_close_at", "at", "date"):
            if key in value:
                return _parse_timestamp(value[key])
        return None
    return _parse_timestamp(value)


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, date):
        return datetime.combine(value, time.max, tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return _as_utc(datetime.fromisoformat(normalized.replace("Z", "+00:00")))
    except ValueError:
        try:
            return datetime.combine(date.fromisoformat(normalized), time.max, tzinfo=timezone.utc)
        except ValueError:
            return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
