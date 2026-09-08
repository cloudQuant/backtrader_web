"""Pure, calendar-backed coverage planning for committed market observations.

This module deliberately knows nothing about database tables, provider APIs, or
legacy coverage summaries.  Callers supply a frozen calendar snapshot and the
observations selected from their committed version; the planner then reports
only the exact missing calendar events in a half-open time window.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.market_data.field_quality import is_usable_field_value

UTC = timezone.utc


class CoverageStatus(str, Enum):
    """The evidence state for a coverage evaluation."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNKNOWN_CALENDAR = "unknown_calendar"


class CalendarStatus(str, Enum):
    """Whether the calendar contains a complete, authoritative event set."""

    KNOWN = "known"
    UNKNOWN = "unknown"


class ObservationQuality(str, Enum):
    """Quality disposition assigned before an observation is considered."""

    PASS = "pass"
    WARNING = "warning"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    UNKNOWN = "unknown"


class GapPosition(str, Enum):
    """A missing run's position among the expected calendar events."""

    HEAD = "head"
    MIDDLE = "middle"
    TAIL = "tail"
    FULL = "full"


class ObservationRejectionReason(str, Enum):
    """Reasons an observation cannot satisfy a coverage requirement."""

    IDENTITY_MISMATCH = "identity_mismatch"
    OUTSIDE_EXPECTED_CALENDAR = "outside_expected_calendar"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    QUALITY_INELIGIBLE = "quality_ineligible"
    NOT_AVAILABLE_AT_CUTOFF = "not_available_at_cutoff"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class QueryIdentity:
    """The complete semantic identity that an observation must match exactly."""

    dataset_code: str
    canonical_id: str
    asset_type: str
    instrument_metadata_version: str
    data_kind: str
    market: str
    frequency: str
    source_policy_id: str
    adjustment: str | None = None
    price_basis: str | None = None
    currency: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "dataset_code",
            "canonical_id",
            "asset_type",
            "instrument_metadata_version",
            "data_kind",
            "market",
            "frequency",
            "source_policy_id",
        ):
            _require_nonempty_string(field_name, getattr(self, field_name))
        for field_name in ("adjustment", "price_basis", "currency", "unit"):
            value = getattr(self, field_name)
            if value is not None:
                _require_nonempty_string(field_name, value)


@dataclass(frozen=True, slots=True, order=True)
class EventKey:
    """One normalized, UTC event instant from an explicit calendar snapshot."""

    event_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_at", _as_utc(self.event_at, field_name="event_at"))


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """An explicit half-open UTC time window: ``[start_at, end_at)``."""

    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        start_at = _as_utc(self.start_at, field_name="start_at")
        end_at = _as_utc(self.end_at, field_name="end_at")
        if start_at >= end_at:
            raise ValueError("start_at must be earlier than end_at")
        object.__setattr__(self, "start_at", start_at)
        object.__setattr__(self, "end_at", end_at)

    def contains(self, event_key: EventKey) -> bool:
        """Return whether an event belongs to this half-open window."""
        return self.start_at <= event_key.event_at < self.end_at


@dataclass(frozen=True, slots=True)
class CalendarSnapshot:
    """A versioned source of expected events without weekday inference.

    ``event_keys`` must be complete for the advertised calendar/version.  An
    empty known snapshot can prove that a requested window has no sessions;
    an unknown snapshot can never prove complete coverage.
    """

    calendar_id: str
    calendar_version: str
    timezone_name: str
    coverage_window: TimeWindow | None = None
    event_keys: tuple[EventKey, ...] = ()
    status: CalendarStatus = CalendarStatus.UNKNOWN
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_nonempty_string("calendar_id", self.calendar_id)
        _require_nonempty_string("calendar_version", self.calendar_version)
        _require_timezone_name(self.timezone_name)
        status = CalendarStatus(self.status)
        if self.coverage_window is not None and not isinstance(self.coverage_window, TimeWindow):
            raise TypeError("coverage_window must be a TimeWindow")
        event_keys = tuple(self.event_keys)
        if any(not isinstance(event_key, EventKey) for event_key in event_keys):
            raise TypeError("event_keys must contain EventKey values")
        ordered_keys = tuple(sorted(event_keys))
        if len(set(ordered_keys)) != len(ordered_keys):
            raise ValueError("calendar snapshot cannot contain duplicate event keys")
        if status is CalendarStatus.UNKNOWN and ordered_keys:
            raise ValueError("an unknown calendar cannot advertise authoritative event keys")
        if status is CalendarStatus.UNKNOWN and self.coverage_window is not None:
            raise ValueError("an unknown calendar cannot advertise a coverage window")
        if status is CalendarStatus.KNOWN and self.coverage_window is None:
            raise ValueError("a known calendar requires an explicit coverage window")
        if self.reason is not None:
            _require_nonempty_string("reason", self.reason)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "event_keys", ordered_keys)

    @classmethod
    def unknown(
        cls,
        *,
        calendar_id: str,
        calendar_version: str,
        timezone_name: str,
        reason: str,
    ) -> CalendarSnapshot:
        """Construct a typed absence of usable calendar evidence."""
        return cls(
            calendar_id=calendar_id,
            calendar_version=calendar_version,
            timezone_name=timezone_name,
            status=CalendarStatus.UNKNOWN,
            reason=reason,
        )

    def covers(self, window: TimeWindow) -> bool:
        """Return whether this snapshot proves its event set for the whole window."""
        return (
            self.status is CalendarStatus.KNOWN
            and self.coverage_window is not None
            and self.coverage_window.start_at <= window.start_at
            and window.end_at <= self.coverage_window.end_at
        )

    def expected_event_keys(self, window: TimeWindow) -> tuple[EventKey, ...]:
        """Return this snapshot's calendar events in ``[start_at, end_at)``."""
        if not self.covers(window):
            return ()
        return tuple(event_key for event_key in self.event_keys if window.contains(event_key))


@dataclass(frozen=True, slots=True)
class Observation:
    """A candidate observation and the evidence needed for PIT eligibility."""

    identity: QueryIdentity
    event_key: EventKey
    fields: Mapping[str, object]
    quality: ObservationQuality = ObservationQuality.UNKNOWN
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, QueryIdentity):
            raise TypeError("identity must be a QueryIdentity")
        if not isinstance(self.event_key, EventKey):
            raise TypeError("event_key must be an EventKey")
        if not isinstance(self.fields, Mapping):
            raise TypeError("fields must be a mapping")
        copied_fields = dict(self.fields)
        if any(not isinstance(name, str) or not name.strip() for name in copied_fields):
            raise ValueError("fields must have non-empty string names")
        object.__setattr__(self, "fields", MappingProxyType(copied_fields))
        object.__setattr__(self, "quality", ObservationQuality(self.quality))
        if self.available_at is not None:
            object.__setattr__(
                self,
                "available_at",
                _as_utc(self.available_at, field_name="available_at"),
            )


@dataclass(frozen=True, slots=True)
class CoverageGap:
    """One contiguous run of missing expected events and its fetch interval."""

    position: GapPosition
    event_keys: tuple[EventKey, ...]
    fetch_window: TimeWindow

    def __post_init__(self) -> None:
        if not self.event_keys:
            raise ValueError("a coverage gap must contain at least one event key")


@dataclass(frozen=True, slots=True)
class CoveragePlan:
    """The deterministic local coverage result for one semantic query identity."""

    status: CoverageStatus
    expected_event_keys: tuple[EventKey, ...]
    accepted_event_keys: tuple[EventKey, ...]
    missing_event_keys: tuple[EventKey, ...]
    gaps: tuple[CoverageGap, ...]
    rejection_counts: Mapping[str, int]
    calendar_reason: str | None = None

    @property
    def coverage_ratio(self) -> float | None:
        """Return the exact accepted/expected ratio when calendar evidence exists."""
        if self.status is CoverageStatus.UNKNOWN_CALENDAR:
            return None
        if not self.expected_event_keys:
            return 1.0
        return len(self.accepted_event_keys) / len(self.expected_event_keys)


class CoveragePlanner:
    """Evaluate observations against a frozen calendar without I/O or inference."""

    def plan(
        self,
        *,
        query: QueryIdentity,
        window: TimeWindow,
        calendar: CalendarSnapshot | None,
        observations: Iterable[Observation],
        required_fields: frozenset[str],
        as_of: datetime,
        eligible_qualities: frozenset[ObservationQuality] = frozenset({ObservationQuality.PASS}),
    ) -> CoveragePlan:
        """Return exact eligible coverage for ``query`` in ``window``.

        The supplied ``as_of`` is a knowledge cutoff.  An observation with an
        unknown or later ``available_at`` cannot be used to prove coverage.
        """
        if not isinstance(query, QueryIdentity):
            raise TypeError("query must be a QueryIdentity")
        if not isinstance(window, TimeWindow):
            raise TypeError("window must be a TimeWindow")
        cutoff = _as_utc(as_of, field_name="as_of")
        normalized_required_fields = _normalize_required_fields(required_fields)
        normalized_qualities = frozenset(ObservationQuality(item) for item in eligible_qualities)
        if not normalized_qualities:
            raise ValueError("eligible_qualities cannot be empty")

        if calendar is None or not calendar.covers(window):
            reason = "calendar_not_supplied" if calendar is None else calendar.reason
            if calendar is not None and calendar.status is CalendarStatus.KNOWN and reason is None:
                reason = "calendar_window_not_covered"
            return CoveragePlan(
                status=CoverageStatus.UNKNOWN_CALENDAR,
                expected_event_keys=(),
                accepted_event_keys=(),
                missing_event_keys=(),
                gaps=(),
                rejection_counts=MappingProxyType({}),
                calendar_reason=reason,
            )

        expected_event_keys = calendar.expected_event_keys(window)
        expected_set = frozenset(expected_event_keys)
        accepted_keys: set[EventKey] = set()
        rejection_counts: Counter[str] = Counter()

        for observation in observations:
            if not isinstance(observation, Observation):
                raise TypeError("observations must contain Observation values")
            rejection_reasons = _observation_rejection_reasons(
                observation=observation,
                query=query,
                expected_event_keys=expected_set,
                required_fields=normalized_required_fields,
                eligible_qualities=normalized_qualities,
                cutoff=cutoff,
            )
            if rejection_reasons:
                rejection_counts.update(reason.value for reason in rejection_reasons)
                continue
            accepted_keys.add(observation.event_key)

        accepted_event_keys = tuple(
            event_key for event_key in expected_event_keys if event_key in accepted_keys
        )
        missing_event_keys = tuple(
            event_key for event_key in expected_event_keys if event_key not in accepted_keys
        )
        gaps = _build_gaps(expected_event_keys, accepted_keys, window)
        status = CoverageStatus.COMPLETE if not missing_event_keys else CoverageStatus.INCOMPLETE
        return CoveragePlan(
            status=status,
            expected_event_keys=expected_event_keys,
            accepted_event_keys=accepted_event_keys,
            missing_event_keys=missing_event_keys,
            gaps=gaps,
            rejection_counts=MappingProxyType(dict(sorted(rejection_counts.items()))),
        )


class SnapshotCoveragePlanner:
    """Evaluate one locally persisted quote snapshot without inventing a calendar.

    A quote is not a bar and must not be forced through a trading-session grid.
    It is complete only when the local store contains an exact, usable snapshot
    in the requested window that is no older than the server-owned freshness
    threshold at the read cutoff.  The planner deliberately returns a single
    full-window gap on a miss so the query service can make one bounded,
    current-only provider request instead of fabricating calendar events.
    """

    def plan(
        self,
        *,
        query: QueryIdentity,
        window: TimeWindow,
        observations: Iterable[Observation],
        required_fields: frozenset[str],
        as_of: datetime,
        max_age: timedelta,
        eligible_qualities: frozenset[ObservationQuality] = frozenset({ObservationQuality.PASS}),
    ) -> CoveragePlan:
        """Return exact local snapshot freshness evidence for one request."""
        if not isinstance(query, QueryIdentity):
            raise TypeError("query must be a QueryIdentity")
        if not isinstance(window, TimeWindow):
            raise TypeError("window must be a TimeWindow")
        if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
            raise ValueError("max_age must be a positive timedelta")
        cutoff = _as_utc(as_of, field_name="as_of")
        normalized_required_fields = _normalize_required_fields(required_fields)
        normalized_qualities = frozenset(ObservationQuality(item) for item in eligible_qualities)
        if not normalized_qualities:
            raise ValueError("eligible_qualities cannot be empty")

        freshness_floor = cutoff - max_age
        accepted: list[Observation] = []
        rejection_counts: Counter[str] = Counter()
        for observation in observations:
            if not isinstance(observation, Observation):
                raise TypeError("observations must contain Observation values")
            rejection_reasons = _snapshot_observation_rejection_reasons(
                observation=observation,
                query=query,
                window=window,
                required_fields=normalized_required_fields,
                eligible_qualities=normalized_qualities,
                cutoff=cutoff,
                freshness_floor=freshness_floor,
            )
            if rejection_reasons:
                rejection_counts.update(reason.value for reason in rejection_reasons)
                continue
            accepted.append(observation)

        if accepted:
            selected = max(
                accepted,
                key=lambda item: (
                    item.event_key.event_at,
                    item.available_at or datetime.min.replace(tzinfo=UTC),
                ),
            )
            return CoveragePlan(
                status=CoverageStatus.COMPLETE,
                expected_event_keys=(selected.event_key,),
                accepted_event_keys=(selected.event_key,),
                missing_event_keys=(),
                gaps=(),
                rejection_counts=MappingProxyType(dict(sorted(rejection_counts.items()))),
            )

        # The marker is inside the half-open window, but is only a missing
        # coverage token; it is never persisted or presented as a source row.
        missing_key = EventKey(window.end_at - timedelta(microseconds=1))
        return CoveragePlan(
            status=CoverageStatus.INCOMPLETE,
            expected_event_keys=(missing_key,),
            accepted_event_keys=(),
            missing_event_keys=(missing_key,),
            gaps=(
                CoverageGap(
                    position=GapPosition.FULL,
                    event_keys=(missing_key,),
                    fetch_window=window,
                ),
            ),
            rejection_counts=MappingProxyType(dict(sorted(rejection_counts.items()))),
            calendar_reason="SNAPSHOT_FRESHNESS_INCOMPLETE",
        )


def _observation_rejection_reasons(
    *,
    observation: Observation,
    query: QueryIdentity,
    expected_event_keys: frozenset[EventKey],
    required_fields: frozenset[str],
    eligible_qualities: frozenset[ObservationQuality],
    cutoff: datetime,
) -> tuple[ObservationRejectionReason, ...]:
    reasons: list[ObservationRejectionReason] = []
    if observation.identity != query:
        reasons.append(ObservationRejectionReason.IDENTITY_MISMATCH)
    if observation.event_key not in expected_event_keys:
        reasons.append(ObservationRejectionReason.OUTSIDE_EXPECTED_CALENDAR)
    if any(
        not is_usable_field_value(field_name, observation.fields.get(field_name))
        for field_name in required_fields
    ):
        reasons.append(ObservationRejectionReason.MISSING_REQUIRED_FIELDS)
    if observation.quality not in eligible_qualities:
        reasons.append(ObservationRejectionReason.QUALITY_INELIGIBLE)
    if observation.available_at is None or observation.available_at > cutoff:
        reasons.append(ObservationRejectionReason.NOT_AVAILABLE_AT_CUTOFF)
    return tuple(reasons)


def _snapshot_observation_rejection_reasons(
    *,
    observation: Observation,
    query: QueryIdentity,
    window: TimeWindow,
    required_fields: frozenset[str],
    eligible_qualities: frozenset[ObservationQuality],
    cutoff: datetime,
    freshness_floor: datetime,
) -> tuple[ObservationRejectionReason, ...]:
    """Reject a quote for identity, window, quality, PIT, or freshness drift."""
    reasons: list[ObservationRejectionReason] = []
    if observation.identity != query:
        reasons.append(ObservationRejectionReason.IDENTITY_MISMATCH)
    if not window.contains(observation.event_key):
        reasons.append(ObservationRejectionReason.OUTSIDE_EXPECTED_CALENDAR)
    if any(
        not is_usable_field_value(field_name, observation.fields.get(field_name))
        for field_name in required_fields
    ):
        reasons.append(ObservationRejectionReason.MISSING_REQUIRED_FIELDS)
    if observation.quality not in eligible_qualities:
        reasons.append(ObservationRejectionReason.QUALITY_INELIGIBLE)
    if observation.available_at is None or observation.available_at > cutoff:
        reasons.append(ObservationRejectionReason.NOT_AVAILABLE_AT_CUTOFF)
    if observation.event_key.event_at > cutoff or observation.event_key.event_at < freshness_floor:
        reasons.append(ObservationRejectionReason.STALE)
    return tuple(reasons)


def _build_gaps(
    expected_event_keys: tuple[EventKey, ...],
    accepted_keys: set[EventKey],
    window: TimeWindow,
) -> tuple[CoverageGap, ...]:
    gaps: list[CoverageGap] = []
    gap_start_index: int | None = None
    for index, event_key in enumerate(expected_event_keys):
        if event_key not in accepted_keys:
            if gap_start_index is None:
                gap_start_index = index
            continue
        if gap_start_index is not None:
            gaps.append(_make_gap(expected_event_keys, gap_start_index, index - 1, window))
            gap_start_index = None
    if gap_start_index is not None:
        gaps.append(
            _make_gap(expected_event_keys, gap_start_index, len(expected_event_keys) - 1, window)
        )
    return tuple(gaps)


def _make_gap(
    expected_event_keys: tuple[EventKey, ...],
    start_index: int,
    end_index: int,
    window: TimeWindow,
) -> CoverageGap:
    last_index = len(expected_event_keys) - 1
    if start_index == 0 and end_index == last_index:
        position = GapPosition.FULL
    elif start_index == 0:
        position = GapPosition.HEAD
    elif end_index == last_index:
        position = GapPosition.TAIL
    else:
        position = GapPosition.MIDDLE
    end_at = (
        expected_event_keys[end_index + 1].event_at if end_index < last_index else window.end_at
    )
    return CoverageGap(
        position=position,
        event_keys=expected_event_keys[start_index : end_index + 1],
        fetch_window=TimeWindow(
            start_at=expected_event_keys[start_index].event_at,
            end_at=end_at,
        ),
    )


def _normalize_required_fields(required_fields: frozenset[str]) -> frozenset[str]:
    if not isinstance(required_fields, frozenset):
        raise TypeError("required_fields must be a frozenset")
    for field_name in required_fields:
        _require_nonempty_string("required field", field_name)
    return required_fields


def _as_utc(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _require_nonempty_string(field_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_timezone_name(timezone_name: str) -> None:
    _require_nonempty_string("timezone_name", timezone_name)
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"timezone_name is not a known IANA timezone: {timezone_name!r}") from exc
