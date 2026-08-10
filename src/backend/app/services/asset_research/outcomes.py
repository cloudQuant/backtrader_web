"""Point-in-time scoring of immutable multi-asset research predictions.

The evaluator intentionally consumes the candidate decision only inside the
restricted service boundary.  Public APIs receive aggregate quality metrics
and published decisions, never the candidate direction or its probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_research import (
    AssetInstrument,
    AssetSignalOutcome,
    AssetSignalPrediction,
    AssetSourceSnapshot,
)
from app.schemas.asset_research import (
    FxIdentityDetails,
    InstrumentIdentity,
    RawAssetSnapshot,
    ResearchDecision,
)
from app.services.asset_research.plugins.fx.quotes import (
    FxExecutionInput,
    calculate_fx_execution_return,
)
from app.services.asset_research.plugins.option.costs import parse_option_cost_snapshot
from app.services.asset_research.plugins.option.pricing import (
    build_option_pricing_input,
    solve_implied_volatility,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _fields_from_record(record: AssetSourceSnapshot) -> dict[str, Any]:
    """Read only the frozen source fields, not a reinterpreted current payload."""
    payload = dict(record.raw_fields_json or {})
    fields = payload.get("fields")
    return dict(fields) if isinstance(fields, dict) else payload


def _snapshot_fields(snapshot: RawAssetSnapshot) -> dict[str, Any]:
    return dict(snapshot.raw_fields or {})


def _same_exact_option_contract(
    entry_identity: InstrumentIdentity,
    observed_identity: InstrumentIdentity,
) -> bool:
    """Require all frozen option terms to agree, not only a potentially stale key."""
    if (
        entry_identity.asset_type != "option"
        or observed_identity.asset_type != "option"
        or entry_identity.identity_level != "CONTRACT"
        or observed_identity.identity_level != "CONTRACT"
        or entry_identity.canonical_id != observed_identity.canonical_id
        or entry_identity.metadata_version != observed_identity.metadata_version
    ):
        return False
    return entry_identity.matches_frozen_identity(observed_identity)


def _nested_value(fields: dict[str, Any], *names: str) -> Decimal | None:
    """Read a named observed value without manufacturing a mid or a default zero."""
    containers: list[dict[str, Any]] = [fields]
    for key in (
        "snapshot",
        "market",
        "valuation",
        "bond",
        "fund",
        "futures",
        "option",
        "fx",
        "crypto",
    ):
        value = fields.get(key)
        if isinstance(value, dict):
            containers.append(value)
    for name in names:
        for container in containers:
            parsed = _decimal(container.get(name))
            if parsed is not None:
                return parsed
    return None


def _nested_boolean(fields: dict[str, Any], name: str) -> bool | None:
    for container in _field_containers(fields):
        value = container.get(name)
        if isinstance(value, bool):
            return value
    return None


def _nested_text(fields: dict[str, Any], name: str) -> str | None:
    for container in _field_containers(fields):
        value = container.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _field_containers(fields: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = [fields]
    for key in (
        "snapshot",
        "market",
        "valuation",
        "bond",
        "fund",
        "futures",
        "option",
        "fx",
        "crypto",
    ):
        value = fields.get(key)
        if isinstance(value, dict):
            containers.append(value)
    return containers


@dataclass(frozen=True, slots=True)
class _Score:
    status: str
    reason_codes: list[str]
    maturity_reason: str | None = None
    entry_price: Decimal | None = None
    entry_price_basis: str | None = None
    exit_price: Decimal | None = None
    exit_price_basis: str | None = None
    gross_return: Decimal | None = None
    net_return: Decimal | None = None
    total_cost: Decimal | None = None
    success_label: bool | None = None
    metrics: dict[str, Any] | None = None


class AssetOutcomeEvaluator:
    """Finalize due outcomes from a newly collected, point-in-time snapshot.

    The caller is responsible for collecting the observed snapshot through the
    licensed source policy and for persisting that raw snapshot before invoking
    this evaluator.  This class deliberately makes no network, LLM, account or
    order calls.
    """

    EVALUATOR_VERSION = "asset-outcome-evaluator-v2"

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def score_prediction(
        self,
        *,
        prediction_id: str,
        observed_snapshot: RawAssetSnapshot,
    ) -> list[AssetSignalOutcome]:
        """Idempotently score due rows for one prediction from one legal snapshot."""
        prediction = await self._db.get(AssetSignalPrediction, prediction_id)
        if prediction is None:
            return []
        entry_snapshot = await self._db.get(AssetSourceSnapshot, prediction.snapshot_id)
        if entry_snapshot is None:
            return []
        entry_instrument = await self._db.get(AssetInstrument, entry_snapshot.instrument_id)
        entry_identity: InstrumentIdentity | None = None
        if entry_instrument is not None:
            try:
                entry_identity = InstrumentIdentity.model_validate(entry_instrument.identity_json)
            except ValueError:
                # An old/corrupt persistence row must never be reinterpreted
                # as a different contract when its outcome becomes due.
                entry_identity = None
        outcomes = list(
            (
                await self._db.execute(
                    select(AssetSignalOutcome)
                    .where(AssetSignalOutcome.prediction_id == prediction.id)
                    .order_by(AssetSignalOutcome.outcome_kind, AssetSignalOutcome.evaluator_version)
                )
            ).scalars()
        )
        candidate = ResearchDecision.model_validate(prediction.candidate_decision_json)
        for outcome in outcomes:
            if outcome.status != "PENDING":
                continue
            score = self._evaluate(
                prediction=prediction,
                candidate=candidate,
                outcome=outcome,
                entry_fields=_fields_from_record(entry_snapshot),
                entry_identity=entry_identity,
                entry_cutoff_at=entry_snapshot.cutoff_at,
                observed_snapshot=observed_snapshot,
            )
            self._apply_score(
                outcome,
                score,
                entry_cutoff_at=entry_snapshot.cutoff_at,
                observed_snapshot=observed_snapshot,
            )
        await self._db.flush()
        return outcomes

    async def mark_due_source_license_blocked(
        self,
        *,
        prediction_id: str,
        evaluated_at: datetime,
    ) -> list[AssetSignalOutcome]:
        """Close only due heads when their frozen source is no longer legal.

        No new observation is required to establish that a source license is
        absent.  Keeping later-maturing heads pending permits a future lawful
        evaluation if the source authorization is renewed before they mature.
        """
        cutoff = _as_utc(evaluated_at)
        due_outcomes = list(
            (
                await self._db.execute(
                    select(AssetSignalOutcome)
                    .where(
                        AssetSignalOutcome.prediction_id == prediction_id,
                        AssetSignalOutcome.status == "PENDING",
                        AssetSignalOutcome.maturity_at.is_not(None),
                        AssetSignalOutcome.maturity_at <= cutoff,
                    )
                    .order_by(AssetSignalOutcome.outcome_kind, AssetSignalOutcome.id)
                )
            ).scalars()
        )
        for outcome in due_outcomes:
            outcome.status = "UNSCORABLE"
            outcome.reason_codes_json = list(
                dict.fromkeys([*(outcome.reason_codes_json or []), "COMMON.SOURCE_LICENSE_BLOCKED"])
            )
            outcome.scored_at = cutoff
        await self._db.flush()
        return due_outcomes

    def _evaluate(
        self,
        *,
        prediction: AssetSignalPrediction,
        candidate: ResearchDecision,
        outcome: AssetSignalOutcome,
        entry_fields: dict[str, Any],
        entry_identity: InstrumentIdentity | None,
        entry_cutoff_at: datetime,
        observed_snapshot: RawAssetSnapshot,
    ) -> _Score:
        if _as_utc(entry_cutoff_at) != _as_utc(prediction.as_of_at):
            return _Score(
                status="UNSCORABLE",
                reason_codes=["COMMON.OUTCOME_ENTRY_CUTOFF_MISMATCH"],
            )
        if entry_identity is None:
            return _Score(
                status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_ENTRY_IDENTITY_MISSING"]
            )
        if (
            entry_identity.canonical_id != prediction.canonical_id
            or entry_identity.asset_type != prediction.asset_type
            or entry_identity.metadata_version != prediction.identity_version
        ):
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"])
        if observed_snapshot.identity.canonical_id != prediction.canonical_id:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"])
        if observed_snapshot.identity.asset_type != prediction.asset_type:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"])
        if observed_snapshot.identity.metadata_version != prediction.identity_version:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"])
        if prediction.asset_type == "option" and not _same_exact_option_contract(
            entry_identity, observed_snapshot.identity
        ):
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"])
        license_status = str(
            observed_snapshot.source_manifest.get("license_status") or "UNKNOWN"
        ).upper()
        if license_status not in {"APPROVED", "RESEARCH_APPROVED"}:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.SOURCE_LICENSE_BLOCKED"])
        if outcome.maturity_at is None:
            # A session horizon without a frozen source calendar is not due.
            # Manual callers must not bypass the durable scheduler's
            # ``maturity_at IS NOT NULL`` claim predicate.
            return _Score(status="PENDING", reason_codes=["COMMON.CALENDAR_UNAVAILABLE"])
        if outcome.maturity_at is not None and _as_utc(observed_snapshot.cutoff_at) < _as_utc(
            outcome.maturity_at
        ):
            return _Score(status="PENDING", reason_codes=["COMMON.OUTCOME_NOT_MATURED"])

        head = next(
            (
                item
                for item in candidate.prediction_heads
                if item.head_spec_hash == outcome.head_spec_hash
            ),
            None,
        )
        if head is None:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_HEAD_SPEC_MISSING"])

        explicit = self._explicit_event_score(outcome.outcome_kind, observed_snapshot)
        if explicit is not None:
            return self._score_explicit_event(candidate, head.probabilities, explicit)
        if outcome.outcome_kind.endswith("event") or outcome.outcome_kind.endswith("risk_path"):
            return _Score(
                status="PARTIAL",
                reason_codes=["COMMON.OUTCOME_EVENT_DATA_PENDING"],
                metrics={"head_kind": "event_or_path"},
            )
        option_score = self._score_option_head(
            outcome_kind=outcome.outcome_kind,
            probabilities=head.probabilities,
            entry_fields=entry_fields,
            observed_fields=_snapshot_fields(observed_snapshot),
            entry_identity=entry_identity,
            entry_cutoff_at=entry_cutoff_at,
            observed_identity=observed_snapshot.identity,
            observed_cutoff_at=observed_snapshot.cutoff_at,
            cost_snapshot=prediction.cost_snapshot_json,
        )
        if option_score is not None:
            return option_score

        direction = candidate.normalized_direction
        if direction not in {"LONG", "SHORT"}:
            return _Score(
                status="UNSCORABLE",
                reason_codes=["COMMON.OUTCOME_NOT_ACTIONABLE"],
                metrics={"candidate_direction": direction},
            )
        if prediction.asset_type == "fx":
            return self._score_fx_execution(
                direction=direction,
                outcome_kind=outcome.outcome_kind,
                probabilities=head.probabilities,
                entry_fields=entry_fields,
                observed_fields=_snapshot_fields(observed_snapshot),
                identity=entry_identity,
                cost_snapshot=prediction.cost_snapshot_json,
                primary_for_promotion=head.primary_for_promotion,
            )
        return self._score_standard_execution(
            asset_type=prediction.asset_type,
            outcome_kind=outcome.outcome_kind,
            direction=direction,
            probabilities=head.probabilities,
            entry_fields=entry_fields,
            observed_fields=_snapshot_fields(observed_snapshot),
            cost_snapshot=prediction.cost_snapshot_json,
            primary_for_promotion=head.primary_for_promotion,
        )

    @classmethod
    def _score_standard_execution(
        cls,
        *,
        asset_type: str,
        outcome_kind: str,
        direction: str,
        probabilities: dict[str, float],
        entry_fields: dict[str, Any],
        observed_fields: dict[str, Any],
        cost_snapshot: object,
        primary_for_promotion: bool,
    ) -> _Score:
        """Score a non-option executable outcome only with frozen trade costs."""
        quotes = cls._select_quotes(
            asset_type=asset_type,
            outcome_kind=outcome_kind,
            direction=direction,
            entry_fields=entry_fields,
            observed_fields=observed_fields,
        )
        if quotes is None:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_PRICE_MISSING"])
        entry_price, entry_basis, exit_price, exit_basis = quotes
        if entry_price <= 0 or exit_price <= 0:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_PRICE_INVALID"])

        gross_return = (
            exit_price / entry_price - Decimal("1")
            if direction == "LONG"
            else entry_price / exit_price - Decimal("1")
        )
        total_cost = cls._explicit_cost_rate(cost_snapshot)
        if total_cost is None:
            return _Score(
                status="UNSCORABLE",
                reason_codes=["COMMON.OUTCOME_COST_SNAPSHOT_MISSING"],
            )
        net_return = gross_return - total_cost
        observed_label = "LONG" if net_return > 0 else "SHORT" if net_return < 0 else "NEUTRAL"
        success_label = direction == observed_label
        return _Score(
            status="SCORED",
            reason_codes=[],
            entry_price=entry_price,
            entry_price_basis=entry_basis,
            exit_price=exit_price,
            exit_price_basis=exit_basis,
            gross_return=gross_return,
            net_return=net_return,
            total_cost=total_cost,
            success_label=success_label,
            metrics={
                "observed_label": observed_label,
                "candidate_direction": direction,
                "head_code": outcome_kind,
                "is_primary_head": primary_for_promotion,
                "probabilities": probabilities,
            },
        )

    @classmethod
    def _score_fx_execution(
        cls,
        *,
        direction: str,
        outcome_kind: str,
        probabilities: dict[str, float],
        entry_fields: dict[str, Any],
        observed_fields: dict[str, Any],
        identity: InstrumentIdentity,
        cost_snapshot: object,
        primary_for_promotion: bool,
    ) -> _Score:
        """Score FX only after normalising the frozen source quote convention."""
        details = identity.details
        if not isinstance(details, FxIdentityDetails):
            return _Score(status="UNSCORABLE", reason_codes=["FX.PRICE_CONVENTION_UNKNOWN"])
        entry_bid = _nested_value(entry_fields, "bid")
        entry_ask = _nested_value(entry_fields, "ask")
        exit_bid = _nested_value(observed_fields, "bid")
        exit_ask = _nested_value(observed_fields, "ask")
        if entry_bid is None or entry_ask is None or exit_bid is None or exit_ask is None:
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_PRICE_MISSING"])
        execution = calculate_fx_execution_return(
            FxExecutionInput(
                base_currency=details.base_currency,
                quote_currency=details.quote_currency,
                price_convention=details.price_convention,
                direction=direction,
                entry_bid=entry_bid,
                entry_ask=entry_ask,
                exit_bid=exit_bid,
                exit_ask=exit_ask,
            )
        )
        if (
            execution.reason_code is not None
            or execution.entry_price is None
            or execution.entry_price_basis is None
            or execution.exit_price is None
            or execution.exit_price_basis is None
            or execution.gross_return is None
        ):
            return _Score(
                status="UNSCORABLE",
                reason_codes=[execution.reason_code or "FX.QUOTE_INCONSISTENT"],
            )
        total_cost = cls._explicit_cost_rate(cost_snapshot)
        if total_cost is None:
            return _Score(
                status="UNSCORABLE",
                reason_codes=["COMMON.OUTCOME_COST_SNAPSHOT_MISSING"],
            )
        net_return = execution.gross_return - total_cost
        observed_label = "LONG" if net_return > 0 else "SHORT" if net_return < 0 else "NEUTRAL"
        return _Score(
            status="SCORED",
            reason_codes=[],
            entry_price=execution.entry_price,
            entry_price_basis=execution.entry_price_basis,
            exit_price=execution.exit_price,
            exit_price_basis=execution.exit_price_basis,
            gross_return=execution.gross_return,
            net_return=net_return,
            total_cost=total_cost,
            success_label=direction == observed_label,
            metrics={
                "observed_label": observed_label,
                "candidate_direction": direction,
                "head_code": outcome_kind,
                "price_convention": details.price_convention,
                "is_primary_head": primary_for_promotion,
                "probabilities": probabilities,
            },
        )

    @staticmethod
    def _explicit_event_score(outcome_kind: str, snapshot: RawAssetSnapshot) -> bool | None:
        outcomes = snapshot.raw_fields.get("outcomes")
        if not isinstance(outcomes, dict):
            return None
        value = outcomes.get(outcome_kind)
        return value if isinstance(value, bool) else None

    @staticmethod
    def _score_explicit_event(
        candidate: ResearchDecision,
        probabilities: dict[str, float],
        occurred: bool,
    ) -> _Score:
        label = "EVENT" if occurred else "NO_EVENT"
        predicted = (
            max(probabilities, key=lambda label: probabilities[label]) if probabilities else None
        )
        return _Score(
            status="SCORED",
            reason_codes=[],
            success_label=predicted == label,
            metrics={
                "observed_label": label,
                "candidate_direction": candidate.normalized_direction,
                "probabilities": probabilities,
                "is_primary_head": False,
            },
        )

    @classmethod
    def _score_option_head(
        cls,
        *,
        outcome_kind: str,
        probabilities: dict[str, float],
        entry_fields: dict[str, Any],
        observed_fields: dict[str, Any],
        entry_identity: InstrumentIdentity | None = None,
        entry_cutoff_at: datetime | None = None,
        observed_identity: InstrumentIdentity | None = None,
        observed_cutoff_at: datetime | None = None,
        cost_snapshot: object = None,
    ) -> _Score | None:
        """Score option directional/IV heads from their own observable, not option P&L."""
        if outcome_kind == "option.underlying_direction":
            entry = _nested_value(
                entry_fields, "underlying_price", "underlying_mark", "underlying_close"
            )
            exit_price = _nested_value(
                observed_fields, "underlying_price", "underlying_mark", "underlying_close"
            )
            if entry is None or exit_price is None:
                return _Score(
                    status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_UNDERLYING_PRICE_MISSING"]
                )
            if entry <= 0 or exit_price <= 0:
                return _Score(
                    status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_UNDERLYING_PRICE_INVALID"]
                )
            change = exit_price / entry - Decimal("1")
            observed_label = (
                "BULLISH"
                if change > Decimal("0.005")
                else "BEARISH"
                if change < Decimal("-0.005")
                else "NEUTRAL"
            )
            return cls._categorical_score(
                probabilities=probabilities,
                observed_label=observed_label,
                head_code=outcome_kind,
                entry_value=entry,
                entry_basis="underlying_price",
                exit_value=exit_price,
                exit_basis="underlying_price",
                metric_name="underlying_return",
                metric_value=change,
            )
        if outcome_kind in {"option.iv_direction", "option.implied_volatility"}:
            if (
                entry_identity is None
                or observed_identity is None
                or entry_cutoff_at is None
                or observed_cutoff_at is None
            ):
                return _Score(
                    status="UNSCORABLE",
                    reason_codes=["OPTION.OUTCOME_IV_PRICING_INPUTS_MISSING"],
                )
            if not _same_exact_option_contract(entry_identity, observed_identity):
                return _Score(
                    status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"]
                )
            last_trade_at = getattr(entry_identity.details, "last_trade_at", None)
            if not isinstance(last_trade_at, datetime):
                return _Score(
                    status="UNSCORABLE",
                    reason_codes=["OPTION.OUTCOME_CONTRACT_LAST_TRADE_MISSING"],
                )
            if _as_utc(entry_cutoff_at) >= _as_utc(last_trade_at) or _as_utc(
                observed_cutoff_at
            ) >= _as_utc(last_trade_at):
                return _Score(
                    status="UNSCORABLE",
                    reason_codes=["OPTION.OUTCOME_IV_CONTRACT_NOT_TRADABLE"],
                )

            entry_quote, entry_quote_reason = cls._option_two_sided_quote(entry_fields)
            observed_quote, observed_quote_reason = cls._option_two_sided_quote(observed_fields)
            if entry_quote is None or observed_quote is None:
                return _Score(
                    status="UNSCORABLE",
                    reason_codes=[
                        entry_quote_reason
                        or observed_quote_reason
                        or "OPTION.OUTCOME_IV_BID_ASK_MISSING"
                    ],
                )
            entry_input, entry_input_reason = build_option_pricing_input(
                identity=entry_identity,
                cutoff_at=entry_cutoff_at,
                raw_fields=entry_fields,
            )
            observed_input, observed_input_reason = build_option_pricing_input(
                identity=observed_identity,
                cutoff_at=observed_cutoff_at,
                raw_fields=observed_fields,
            )
            if entry_input is None or observed_input is None:
                return _Score(
                    status="UNSCORABLE",
                    reason_codes=[
                        entry_input_reason
                        or observed_input_reason
                        or "OPTION.OUTCOME_IV_PRICING_INPUTS_MISSING"
                    ],
                )

            entry_solver = solve_implied_volatility(
                replace(entry_input, volatility=None), observed_price=float(entry_quote[1])
            )
            observed_solver = solve_implied_volatility(
                replace(observed_input, volatility=None), observed_price=float(observed_quote[0])
            )
            if (
                entry_solver.implied_volatility is None
                or observed_solver.implied_volatility is None
            ):
                return _Score(
                    status="UNSCORABLE",
                    reason_codes=["OPTION.OUTCOME_IV_SOLVER_FAILED"],
                    metrics={
                        "entry_solver_reason": entry_solver.reason_code,
                        "exit_solver_reason": observed_solver.reason_code,
                        "entry_pricing_model": entry_input.model,
                        "exit_pricing_model": observed_input.model,
                    },
                )
            entry = Decimal(str(entry_solver.implied_volatility))
            exit_value = Decimal(str(observed_solver.implied_volatility))
            change = exit_value - entry
            observed_label = (
                "VOL_UP"
                if change > Decimal("0.005")
                else "VOL_DOWN"
                if change < Decimal("-0.005")
                else "NEUTRAL"
            )
            return cls._categorical_score(
                probabilities=probabilities,
                observed_label=observed_label,
                head_code=outcome_kind,
                entry_value=entry,
                entry_basis="iv_ask_solver",
                exit_value=exit_value,
                exit_basis="iv_bid_solver",
                metric_name="iv_change",
                metric_value=change,
            )
        if outcome_kind == "option.exact_contract_net_profit":
            return cls._score_option_contract_profit(
                probabilities=probabilities,
                entry_fields=entry_fields,
                observed_fields=observed_fields,
                entry_identity=entry_identity,
                observed_identity=observed_identity,
                entry_cutoff_at=entry_cutoff_at,
                observed_cutoff_at=observed_cutoff_at,
                cost_snapshot=cost_snapshot,
            )
        return None

    @classmethod
    def _score_option_contract_profit(
        cls,
        *,
        probabilities: dict[str, float],
        entry_fields: dict[str, Any],
        observed_fields: dict[str, Any],
        entry_identity: InstrumentIdentity | None,
        observed_identity: InstrumentIdentity | None,
        entry_cutoff_at: datetime | None,
        observed_cutoff_at: datetime | None,
        cost_snapshot: object,
    ) -> _Score:
        """Score one long exact contract; never roll or turn it into a short."""
        if (
            entry_identity is None
            or observed_identity is None
            or entry_cutoff_at is None
            or observed_cutoff_at is None
        ):
            return _Score(
                status="UNSCORABLE",
                reason_codes=["OPTION.OUTCOME_CONTRACT_INPUTS_MISSING"],
            )
        if not _same_exact_option_contract(entry_identity, observed_identity):
            return _Score(status="UNSCORABLE", reason_codes=["COMMON.OUTCOME_IDENTITY_MISMATCH"])
        contract_multiplier = _decimal(getattr(entry_identity.details, "contract_multiplier", None))
        if contract_multiplier is None or contract_multiplier <= 0:
            return _Score(
                status="UNSCORABLE",
                reason_codes=["OPTION.OUTCOME_CONTRACT_MULTIPLIER_INVALID"],
            )
        entry_ask = _nested_value(entry_fields, "ask")
        if entry_ask is None:
            return _Score(status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_ENTRY_ASK_MISSING"])
        if entry_ask <= 0:
            return _Score(status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_ENTRY_ASK_INVALID"])

        expiry_at = getattr(entry_identity.details, "expiry_at", None)
        last_trade_at = getattr(entry_identity.details, "last_trade_at", None)
        if not isinstance(expiry_at, datetime):
            return _Score(
                status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_CONTRACT_EXPIRY_MISSING"]
            )
        if not isinstance(last_trade_at, datetime):
            return _Score(
                status="UNSCORABLE",
                reason_codes=["OPTION.OUTCOME_CONTRACT_LAST_TRADE_MISSING"],
            )
        contract_end_at = min(_as_utc(last_trade_at), _as_utc(expiry_at))
        if _as_utc(entry_cutoff_at) >= contract_end_at:
            return _Score(
                status="UNSCORABLE",
                reason_codes=["OPTION.OUTCOME_CONTRACT_NOT_TRADABLE"],
            )
        is_expiry = _as_utc(observed_cutoff_at) >= contract_end_at
        exit_price: Decimal | None
        exit_basis: str
        if is_expiry:
            settlement = _nested_value(observed_fields, "official_settlement")
            settlement_final = _nested_boolean(observed_fields, "official_settlement_final")
            settlement_rule_version = _nested_text(observed_fields, "settlement_rule_version")
            if (
                settlement is None
                or settlement_final is not True
                or settlement_rule_version is None
            ):
                return _Score(
                    status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_SETTLEMENT_MISSING"]
                )
            if settlement < 0:
                return _Score(
                    status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_SETTLEMENT_INVALID"]
                )
            exit_price = settlement
            exit_basis = "official_settlement"
        else:
            exit_price = _nested_value(observed_fields, "bid")
            if exit_price is None:
                return _Score(status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_EXIT_BID_MISSING"])
            if exit_price <= 0:
                return _Score(status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_EXIT_BID_INVALID"])
            exit_basis = "bid"

        option_costs, cost_reason = parse_option_cost_snapshot(cost_snapshot)
        if option_costs is None:
            return _Score(
                status="UNSCORABLE",
                reason_codes=[cost_reason or "OPTION.COST_SNAPSHOT_MISSING"],
            )
        if exit_price is None:
            return _Score(status="UNSCORABLE", reason_codes=["OPTION.OUTCOME_EXIT_PRICE_MISSING"])
        gross_return = exit_price / entry_ask - Decimal("1")
        applied_cost_fields = [
            key
            for key in option_costs.to_payload()
            if key.endswith("_rate")
            and key != "total_cost_rate"
            and (is_expiry or key != "exercise_settlement_cost_rate")
        ]
        total_cost = sum(
            (Decimal(str(option_costs.to_payload()[key])) for key in applied_cost_fields),
            Decimal("0"),
        )
        net_return = gross_return - total_cost
        gross_pnl = (exit_price - entry_ask) * contract_multiplier
        total_cost_amount = total_cost * entry_ask * contract_multiplier
        net_pnl = gross_pnl - total_cost_amount
        observed_label = "PROFIT" if net_return > 0 else "LOSS"
        predicted = (
            max(probabilities, key=lambda label: probabilities[label]) if probabilities else None
        )
        return _Score(
            status="SCORED",
            reason_codes=[],
            maturity_reason="EXPIRY" if is_expiry else None,
            entry_price=entry_ask,
            entry_price_basis="ask",
            exit_price=exit_price,
            exit_price_basis=exit_basis,
            gross_return=gross_return,
            net_return=net_return,
            total_cost=total_cost,
            success_label=predicted == observed_label,
            metrics={
                "observed_label": observed_label,
                "head_code": "option.exact_contract_net_profit",
                "probabilities": probabilities,
                "is_primary_head": True,
                "cost_model_version": option_costs.cost_model_version,
                "applied_cost_fields": applied_cost_fields,
                "settlement_rule_version": settlement_rule_version if is_expiry else None,
                "last_trade_at": _as_utc(last_trade_at).isoformat(),
                "contract_end_at": contract_end_at.isoformat(),
                "contract_multiplier": float(contract_multiplier),
                "gross_pnl": float(gross_pnl),
                "total_cost_amount": float(total_cost_amount),
                "net_pnl": float(net_pnl),
                "settlement_type": str(getattr(entry_identity.details, "settlement_type", "")),
                "deliverable": str(getattr(entry_identity.details, "deliverable", "")),
                "automatic_exercise_rule": str(
                    getattr(entry_identity.details, "automatic_exercise_rule", "")
                ),
            },
        )

    @staticmethod
    def _option_two_sided_quote(
        fields: dict[str, Any],
    ) -> tuple[tuple[Decimal, Decimal] | None, str | None]:
        """Return a usable bid/ask pair without manufacturing a midpoint."""
        bid = _nested_value(fields, "bid")
        ask = _nested_value(fields, "ask")
        if bid is None or ask is None:
            return None, "OPTION.OUTCOME_IV_BID_ASK_MISSING"
        if bid <= 0 or ask <= 0 or bid > ask:
            return None, "OPTION.OUTCOME_IV_BID_ASK_INVALID"
        return (bid, ask), None

    @staticmethod
    def _categorical_score(
        *,
        probabilities: dict[str, float],
        observed_label: str,
        head_code: str,
        entry_value: Decimal,
        entry_basis: str,
        exit_value: Decimal,
        exit_basis: str,
        metric_name: str,
        metric_value: Decimal,
    ) -> _Score:
        predicted = (
            max(probabilities, key=lambda label: probabilities[label]) if probabilities else None
        )
        return _Score(
            status="SCORED",
            reason_codes=[],
            entry_price=entry_value,
            entry_price_basis=entry_basis,
            exit_price=exit_value,
            exit_price_basis=exit_basis,
            success_label=predicted == observed_label,
            metrics={
                "observed_label": observed_label,
                "head_code": head_code,
                "probabilities": probabilities,
                metric_name: float(metric_value),
                "is_primary_head": False,
            },
        )

    @staticmethod
    def _explicit_cost_rate(cost_snapshot: object) -> Decimal | None:
        """Read an explicitly frozen rate; absent data may not become a free trade."""
        if not isinstance(cost_snapshot, dict):
            return None
        for key in ("total_cost_rate", "cost_rate", "transaction_cost_rate"):
            value = _decimal(cost_snapshot.get(key))
            if value is not None and value >= 0:
                return value
        return None

    @staticmethod
    def _select_quotes(
        *,
        asset_type: str,
        outcome_kind: str,
        direction: str,
        entry_fields: dict[str, Any],
        observed_fields: dict[str, Any],
    ) -> tuple[Decimal, str, Decimal, str] | None:
        """Use the correct executable side when an asset contract requires it."""
        requires_two_sided = asset_type in {"futures", "fx", "option", "crypto"} or (
            asset_type == "bond" and outcome_kind == "bond.executable_total_return"
        )
        if requires_two_sided:
            entry_name, exit_name = ("ask", "bid") if direction == "LONG" else ("bid", "ask")
            entry = _nested_value(entry_fields, entry_name)
            exit_price = _nested_value(observed_fields, exit_name)
            if entry is None or exit_price is None:
                return None
            return entry, entry_name, exit_price, exit_name

        if asset_type == "fund" and outcome_kind == "fund.open_end_nav_return":
            entry = _nested_value(entry_fields, "official_nav", "nav")
            exit_price = _nested_value(observed_fields, "official_nav", "nav")
            basis = "official_nav"
        elif asset_type == "bond" and outcome_kind == "bond.valuation_total_return":
            entry = _nested_value(entry_fields, "official_valuation", "valuation", "price")
            exit_price = _nested_value(observed_fields, "official_valuation", "valuation", "price")
            basis = "official_valuation"
        else:
            entry = _nested_value(
                entry_fields, "price", "nav", "official_nav", "official_valuation"
            )
            exit_price = _nested_value(
                observed_fields, "price", "nav", "official_nav", "official_valuation"
            )
            basis = "observed_price"
        if entry is None or exit_price is None:
            return None
        return entry, basis, exit_price, basis

    @staticmethod
    def _apply_score(
        outcome: AssetSignalOutcome,
        score: _Score,
        *,
        entry_cutoff_at: datetime,
        observed_snapshot: RawAssetSnapshot,
    ) -> None:
        if score.status == "PENDING":
            return
        outcome.status = score.status
        outcome.maturity_reason = score.maturity_reason or (
            "HORIZON_REACHED" if score.status == "SCORED" else outcome.maturity_reason
        )
        # ``maturity_at`` is the frozen horizon boundary, not the time an
        # eventually available observed snapshot happened to be collected.
        # Keep it stable so scorecard cohorts and late-data diagnostics retain
        # their original temporal meaning.
        outcome.entry_at = _as_utc(entry_cutoff_at)
        outcome.exit_at = _as_utc(observed_snapshot.cutoff_at)
        outcome.entry_price = score.entry_price
        outcome.entry_price_basis = score.entry_price_basis
        outcome.exit_price = score.exit_price
        outcome.exit_price_basis = score.exit_price_basis
        outcome.currency = observed_snapshot.identity.currency
        outcome.gross_return = score.gross_return
        outcome.net_return = score.net_return
        outcome.total_cost = score.total_cost
        outcome.success_label = score.success_label
        outcome.metrics_json = score.metrics or {}
        outcome.reason_codes_json = score.reason_codes
        outcome.scored_at = _now()


def _now() -> datetime:
    return datetime.now(timezone.utc)
