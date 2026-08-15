"""Shared immutable configuration for concrete asset research plugins."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from statistics import fmean
from typing import Any

from app.schemas.asset_research import (
    BondResearchDetails,
    CryptoResearchDetails,
    EligibleAssetSnapshot,
    FeatureSet,
    FundResearchDetails,
    FuturesResearchDetails,
    FxIdentityDetails,
    FxResearchDetails,
    HorizonSpec,
    OptionResearchDetails,
    OutcomeEvaluation,
    PredictionHead,
    QualityAssessment,
    RawAssetSnapshot,
    ReportSection,
    ResearchDecision,
)
from app.services.asset_research.calendar import resolve_horizon_maturity
from app.services.asset_research.data import canonical_json_hash
from app.services.asset_research.plugins.bond.valuation import (
    BondCashflow,
    BondValuationInput,
    calculate_fixed_rate_bond_analytics,
)
from app.services.asset_research.plugins.crypto.market_quality import (
    CryptoMarketQualityInput,
    CryptoVenueQuote,
    calculate_crypto_market_quality,
)
from app.services.asset_research.plugins.fund.metrics import (
    BenchmarkPoint,
    FundMetricsInput,
    FundNavPoint,
    calculate_fund_metrics,
)
from app.services.asset_research.plugins.futures.term_structure import (
    FuturesTermStructureInput,
    calculate_futures_term_structure,
)
from app.services.asset_research.plugins.option.chain import (
    parse_option_chain_quality_policy,
    parse_option_chain_timestamp,
    validate_option_chain,
)
from app.services.asset_research.plugins.option.costs import parse_option_cost_snapshot
from app.services.asset_research.plugins.option.pricing import (
    OptionPricingInput,
    build_option_pricing_input,
    calculate_option_analytics,
    solve_implied_volatility,
)
from app.services.asset_research.reports import build_asset_report_sections
from app.services.asset_research.types import AssetResearchAssetType, AssetResearchPlugin


@dataclass(frozen=True, slots=True)
class ConfiguredAssetResearchPlugin(AssetResearchPlugin):
    """Asset-specific quality, features, opinion and reporting behavior.

    Plugins contain no database, LLM or order side effect.  The orchestrator
    persists raw and derived facts around these deterministic methods.
    """

    asset_type: AssetResearchAssetType
    reason_codes: tuple[str, ...]

    def assess_quality(self, snapshot: RawAssetSnapshot) -> QualityAssessment:
        """Apply non-interchangeable asset data requirements before any decision."""
        hard_reasons: list[str] = []
        checks: dict[str, bool | str | int | float | None] = {
            "history_rows": len(snapshot.history_rows),
            "license_status": str(snapshot.source_manifest.get("license_status") or "UNKNOWN"),
        }
        pit_status = snapshot.source_manifest.get("point_in_time_status")
        checks["point_in_time_status"] = str(pit_status) if pit_status is not None else None
        if pit_status not in {None, "VERIFIED"}:
            hard_reasons.append("COMMON.PIT_UNVERIFIED")
        snapshot_price = (snapshot.raw_fields.get("snapshot") or {}).get("price")
        closes = self._closing_prices(snapshot)
        if snapshot_price is None and not closes:
            hard_reasons.append("COMMON.INSUFFICIENT_HISTORY")
        if str(snapshot.source_manifest.get("license_status") or "UNKNOWN") not in {
            "APPROVED",
            "RESEARCH_APPROVED",
        }:
            hard_reasons.append("COMMON.SOURCE_LICENSE_BLOCKED")

        capabilities = {
            str(item) for item in snapshot.source_manifest.get("capabilities", []) if str(item)
        }
        required_capabilities = self._required_capabilities(snapshot)
        missing = sorted(required_capabilities - capabilities)
        checks["required_capabilities"] = ",".join(sorted(required_capabilities))
        checks["missing_capabilities"] = ",".join(missing) if missing else None
        if missing:
            hard_reasons.append(self._missing_capability_reason())

        if self.asset_type == "futures" and snapshot.identity.identity_level == "SERIES":
            hard_reasons.append("FUTURES.CONTINUOUS_PRICE_NOT_TRADABLE")
        if self.asset_type == "option" and snapshot.identity.identity_level != "CONTRACT":
            hard_reasons.append("OPTION.CHAIN_INCOMPLETE")

        domain_checks, domain_reasons = self._asset_specific_quality_checks(snapshot)
        checks.update(domain_checks)
        if self.asset_type == "fx" and snapshot.source_manifest.get("quote_kind") == "REFERENCE":
            domain_reasons.append("FX.REFERENCE_ONLY")

        reason_codes = list(dict.fromkeys([*hard_reasons, *domain_reasons]))
        if reason_codes:
            status = (
                "DEGRADED"
                if not hard_reasons
                and set(domain_reasons).issubset(self._degradable_reason_codes(snapshot))
                else "REJECTED"
            )
            return QualityAssessment(
                status=status,
                reason_codes=reason_codes,
                checks=checks,
            )
        return QualityAssessment(status="ELIGIBLE", reason_codes=[], checks=checks)

    def promote_snapshot(
        self, snapshot: RawAssetSnapshot, quality: QualityAssessment
    ) -> EligibleAssetSnapshot | None:
        """Narrow a raw snapshot only after its quality checks approve it."""
        if quality.status == "REJECTED":
            return None
        return EligibleAssetSnapshot(raw_snapshot=snapshot, quality=quality)

    def compute_features(self, snapshot: EligibleAssetSnapshot) -> FeatureSet:
        """Compute common and asset-specific features without zero imputation."""
        raw_snapshot = snapshot.raw_snapshot
        prices = self._closing_prices(raw_snapshot)
        last = prices[-1] if prices else None
        first = prices[max(0, len(prices) - 20)] if prices else None
        momentum = (last / first - 1.0) if last and first else None
        moving_average = fmean(prices[-20:]) if prices else None
        volatility = self._volatility(prices[-20:])
        values: dict[str, float | int | str | None] = {
            "latest_price": last,
            "momentum_20": momentum,
            "moving_average_20": moving_average,
            "volatility_20": volatility,
            "history_count": len(prices),
        }
        values.update(self._asset_feature_values(raw_snapshot))
        provisional = FeatureSet(
            feature_version=f"{self.asset_type}-domain-features-v2",
            values=values,
        )
        domain_score, domain_signal_count = self._domain_signal(provisional, raw_snapshot)
        values["domain_signal_score"] = domain_score
        values["domain_signal_count"] = domain_signal_count
        return FeatureSet(
            feature_version=f"{self.asset_type}-domain-features-v2",
            values=values,
        )

    def make_decision(
        self,
        features: FeatureSet | None,
        quality: QualityAssessment,
        *,
        position_context: str,
        horizon_code: str,
        snapshot: RawAssetSnapshot,
    ) -> ResearchDecision:
        """Return a candidate view; publication gates decide what a user may see."""
        signal_score = features.values.get("domain_signal_score") if features is not None else None
        heads = self._prediction_heads(snapshot=snapshot, signal_score=signal_score)
        if quality.status == "REJECTED" or features is None:
            return ResearchDecision(
                asset_type=self.asset_type,
                market_view="INDETERMINATE",
                normalized_direction="INDETERMINATE",
                position_context=position_context,
                horizon_code=horizon_code,
                quality_status=quality.status,
                recommendation="AVOID",
                actionability="INSUFFICIENT_DATA",
                reason_codes=list(quality.reason_codes),
                horizon_spec=self._horizon_spec(snapshot),
                primary_head_code=self._primary_head_code(snapshot),
                prediction_heads=heads,
                asset_details=self._asset_details(snapshot, features),
            )
        direction = "NEUTRAL"
        market_view = "NEUTRAL"
        numeric_score = self._number(signal_score)
        threshold = self._signal_threshold()
        if numeric_score is not None and numeric_score > threshold:
            direction, market_view = "LONG", "BULLISH"
        elif (
            self.asset_type != "option" and numeric_score is not None and numeric_score < -threshold
        ):
            direction, market_view = "SHORT", "BEARISH"
        research_only_reason = self._research_only_reason(snapshot)
        is_research_only = quality.status == "DEGRADED" or research_only_reason is not None
        reason_codes = list(quality.reason_codes)
        if research_only_reason is not None:
            reason_codes = list(dict.fromkeys([*reason_codes, research_only_reason]))
        return ResearchDecision(
            asset_type=self.asset_type,
            market_view=market_view,
            normalized_direction=direction,
            position_context=position_context,
            horizon_code=horizon_code,
            quality_status=quality.status,
            actionability="RESEARCH_ONLY" if is_research_only else "ACTIONABLE",
            # This is a deterministic shadow rule, not a calibrated model.
            # Keep internal candidate confidence deliberately bounded until
            # the promotion workflow proves a calibrated artifact.
            confidence=self._shadow_confidence(numeric_score, threshold)
            if direction != "NEUTRAL" and not is_research_only
            else None,
            horizon_spec=self._horizon_spec(snapshot),
            primary_head_code=None if is_research_only else self._primary_head_code(snapshot),
            prediction_heads=[] if is_research_only else heads,
            reason_codes=reason_codes,
            asset_details=self._asset_details(snapshot, features),
        )

    def build_report_sections(
        self, snapshot: RawAssetSnapshot, published_decision: ResearchDecision
    ) -> list[ReportSection]:
        """Render only published, not shadow-candidate, facts into the report."""
        return build_asset_report_sections(
            snapshot=snapshot,
            published_decision=published_decision,
        )

    def score_outcome(
        self,
        *,
        decision: ResearchDecision,
        horizon_code: str,
        as_of: datetime,
        snapshot: RawAssetSnapshot,
    ) -> list[OutcomeEvaluation]:
        """Create one pending shell per asset-specific outcome head.

        A result row is deliberately tied to the immutable head specification,
        not merely to an asset type.  This prevents a scorecard from combining
        a bond credit-event probability with an executable total-return head,
        or an option IV head with a contract P&L head.
        """
        if decision.actionability == "RESEARCH_ONLY":
            return []
        heads = decision.prediction_heads or self._prediction_heads(
            snapshot=snapshot, signal_score=None
        )
        maturity = resolve_horizon_maturity(
            snapshot=snapshot,
            horizon_spec=decision.horizon_spec,
            as_of=as_of,
        )
        return [
            OutcomeEvaluation(
                outcome_kind=head.head_code,
                head_spec_hash=head.head_spec_hash,
                horizon_code=horizon_code,
                evaluator_version=f"{self.asset_type}-outcome-v2",
                status="PENDING",
                maturity_at=maturity.maturity_at,
                maturity_reason=maturity.maturity_reason,
                metrics=maturity.metrics,
                reason_codes=maturity.reason_codes,
            )
            for head in heads
        ]

    def _research_only_reason(self, snapshot: RawAssetSnapshot) -> str | None:
        """Return the reason when a generic model may not publish an action.

        An issuer/issue, a venue-free FX pair or a CAIP asset can support a
        factual research report, but it is not an executable product. Some
        confirmed products likewise need their own model family (for example
        perpetual or structured bonds and leveraged funds). Keeping this
        decision at the plugin boundary prevents a future promoted generic
        model from turning either case into a product-level action.
        """
        if self.asset_type == "bond":
            bond = self._mapping(snapshot.raw_fields.get("bond"))
            details = snapshot.identity.details
            if bond.get("is_perpetual") is True or getattr(details, "is_perpetual", None) is True:
                return "BOND.PERPETUAL_MODEL_REQUIRED"
            if bond.get("specialized_model_required") is True:
                return "BOND.SPECIALIZED_MODEL_REQUIRED"
        if self.asset_type == "fund":
            fund = self._mapping(snapshot.raw_fields.get("fund"))
            fund_type = str(fund.get("fund_type") or "").upper()
            if fund.get("specialized_model_required") is True or fund_type in {
                "COMMODITY",
                "COMPLEX",
                "INVERSE",
                "LEVERAGED",
                "LEVERAGED_INVERSE",
            }:
                return "FUND.SPECIALIZED_MODEL_REQUIRED"
        if self.asset_type == "futures" and snapshot.identity.identity_level == "PRODUCT":
            # A product code identifies a market family, not the frozen contract
            # whose expiry, multiplier, costs and outcome prices are required
            # for a published signal.  It may still power factual research.
            return "FUTURES.PRODUCT_LEVEL_RESEARCH_ONLY"
        if snapshot.identity.identity_level != "ASSET":
            return None
        return {
            "bond": "BOND.ASSET_LEVEL_RESEARCH_ONLY",
            "fx": "FX.REFERENCE_ONLY",
            "crypto": "CRYPTO.ASSET_LEVEL_RESEARCH_ONLY",
        }.get(self.asset_type)

    def _degradable_reason_codes(self, snapshot: RawAssetSnapshot) -> set[str]:
        """Return incomplete-but-researchable facts for this exact snapshot.

        A degraded snapshot is never actionable: it retains an auditable
        factual report while the publication gate removes directions, heads and
        trade intent.  The allowlist is intentionally narrow.  Any unknown,
        licensing, identity, timing, quote, or valuation failure remains a
        hard rejection by default.
        """
        del snapshot
        return {
            "bond": {
                "BOND.PERPETUAL_MODEL_REQUIRED",
                "BOND.VALUATION_NOT_EXECUTABLE",
                "COMMON.EVIDENCE_COVERAGE_LOW",
                "BOND.PEER_DATA_INCOMPLETE",
                "BOND.CREDIT_DISCLOSURE_STALE",
            },
            "fund": {
                "FUND.HOLDINGS_STALE",
                "FUND.MANAGEMENT_EVIDENCE_LOW",
                "FUND.SECONDARY_MARKET_DATA_PARTIAL",
                "FUND.SHORT_TRACK_RECORD",
            },
            "futures": {
                "FUTURES.TERM_STRUCTURE_INCOMPLETE",
                "FUTURES.BASIS_ALIGNMENT_PARTIAL",
                "FUTURES.MARKET_CONTEXT_STALE",
                "FUTURES.BROKER_MARGIN_UNKNOWN",
                "FUTURES.FUNDAMENTAL_COVERAGE_LOW",
            },
            "option": {
                "OPTION.SURFACE_COVERAGE_INSUFFICIENT",
                "OPTION.LIQUIDITY_DEGRADED",
                "OPTION.SECONDARY_PRICING_INPUTS_STALE",
            },
            "fx": {
                "FX.REFERENCE_ONLY",
                "FX.MACRO_MISSING",
                "FX.FORWARD_POINTS_MISSING",
                "FX.COT_MISSING",
                "FX.NEWS_COVERAGE_LOW",
                "FX.HISTORY_INSUFFICIENT",
                "FX.CROSS_SOURCE_WARNING",
            },
            "crypto": {
                "CRYPTO.SINGLE_VENUE_REFERENCE",
                "CRYPTO.HISTORY_INSUFFICIENT",
                "CRYPTO.TOKEN_MIGRATION_INCOMPLETE",
                "CRYPTO.ONCHAIN_UNSUPPORTED",
                "CRYPTO.SECONDARY_METRICS_MISSING",
            },
        }[self.asset_type]

    def _outcome_kinds(self, snapshot: RawAssetSnapshot | None) -> tuple[str, ...]:
        """Return the immutable scorecard contract for this concrete product.

        The generic orchestration owns persistence, but it may not decide that
        a fund NAV, a futures roll result, or an option volatility label are
        interchangeable forms of price return.  Product routing happens before
        this method and is frozen in the decision input/snapshot.
        """
        if self.asset_type == "bond":
            return (
                "bond.executable_total_return",
                "bond.valuation_total_return",
                "bond.credit_event",
            )
        if self.asset_type == "fund":
            fund_type = str(
                (snapshot.raw_fields.get("fund") or {}).get("fund_type")
                if snapshot is not None
                else "ETF"
            ).upper()
            primary = {
                "OPEN_END": "fund.open_end_nav_return",
                "MONEY_MARKET": "fund.money_market_cash_return",
                "QDII": "fund.qdii_nav_fx_return",
            }.get(fund_type, "fund.etf_market_return")
            return (primary, "fund.dealing_event")
        if self.asset_type == "futures":
            return (
                "futures.contract_pnl",
                "futures.roll_aware_pnl",
                "futures.close_avoided_loss",
            )
        if self.asset_type == "option":
            return (
                "option.underlying_direction",
                "option.iv_direction",
                "option.exact_contract_net_profit",
                "option.close_avoided_loss",
            )
        if self.asset_type == "fx":
            return ("fx.direction_pnl", "fx.action_utility", "fx.risk_path")
        if snapshot is not None:
            product = getattr(snapshot.identity.details, "market_type", "SPOT")
            if product in {"PERPETUAL", "DELIVERY_FUTURE"}:
                return (
                    "crypto.derivative_pnl",
                    "crypto.liquidation_risk",
                    "crypto.risk_path",
                )
        return ("crypto.spot_pnl", "crypto.benchmark_excess", "crypto.risk_path")

    def _primary_head_code(self, snapshot: RawAssetSnapshot | None) -> str:
        """Keep exactly one promotion head while retaining secondary evidence heads."""
        outcomes = self._outcome_kinds(snapshot)
        if self.asset_type == "option":
            return "option.exact_contract_net_profit"
        return outcomes[0]

    def _prediction_heads(
        self, *, snapshot: RawAssetSnapshot | None, signal_score: object
    ) -> list[PredictionHead]:
        """Freeze every asset-specific head and one explicit promotion primary."""
        primary_head = self._primary_head_code(snapshot)
        return [
            self._prediction_head(
                head_code=head_code,
                primary_for_promotion=head_code == primary_head,
                snapshot=snapshot,
                signal_score=signal_score,
            )
            for head_code in self._outcome_kinds(snapshot)
        ]

    def _prediction_head(
        self,
        *,
        head_code: str,
        primary_for_promotion: bool,
        snapshot: RawAssetSnapshot | None,
        signal_score: object,
    ) -> PredictionHead:
        """Freeze a deterministic shadow head that can later be scored safely."""
        numeric_signal = self._number(signal_score) or 0.0
        threshold = self._signal_threshold()
        target_definition = (
            "Frozen asset-specific target after the configured source calendar, "
            "product convention and costs."
        )
        target_spec_version = "target-v2"
        scoreability_rule = (
            "Only completed, permitted source snapshots with the required "
            "asset-specific observable may be scored."
        )
        scoreability_rule_version = "scoreability-v2"
        if head_code.endswith("event") or head_code.endswith("risk_path"):
            labels = ["EVENT", "NO_EVENT"]
            probabilities = {"EVENT": 0.20, "NO_EVENT": 0.80}
        elif head_code == "option.underlying_direction":
            target_definition = (
                "Exact underlying observation return, with the frozen observation "
                "source, adjustment rule and a strict 0.5% neutral band."
            )
            target_spec_version = "option.underlying_direction.v1"
            scoreability_rule = (
                "Both entry and exit must be permitted exact-underlying observations; "
                "no substitute option mark, stale close or unversioned adjustment is allowed."
            )
            scoreability_rule_version = "option.underlying_direction.scoreability.v1"
            labels = ["BULLISH", "BEARISH", "NEUTRAL"]
            option = self._mapping(snapshot.raw_fields.get("option")) if snapshot else {}
            underlying_return = self._first_number(
                option.get("underlying_return_20"), option.get("underlying_momentum_20")
            )
            if underlying_return is not None and underlying_return > 0.01:
                probabilities = {"BULLISH": 0.58, "BEARISH": 0.18, "NEUTRAL": 0.24}
            elif underlying_return is not None and underlying_return < -0.01:
                probabilities = {"BULLISH": 0.18, "BEARISH": 0.58, "NEUTRAL": 0.24}
            else:
                probabilities = {"BULLISH": 0.20, "BEARISH": 0.20, "NEUTRAL": 0.60}
        elif head_code == "option.iv_direction":
            target_definition = (
                "Exact-contract volatility change: exit bid IV minus entry ask IV, "
                "using the frozen model, day-count and strict 0.5 vol-point neutral band."
            )
            target_spec_version = "option.iv_direction.v1"
            scoreability_rule = (
                "Both times require valid exact-contract bid and ask quotes plus converged "
                "bid/ask IV solvers; mid, ATM, surface and adjacent-contract substitutes fail."
            )
            scoreability_rule_version = "option.iv_direction.scoreability.v1"
            labels = ["VOL_UP", "VOL_DOWN", "NEUTRAL"]
            option = self._mapping(snapshot.raw_fields.get("option")) if snapshot else {}
            iv_change = self._first_number(
                option.get("implied_volatility_change"), option.get("iv_change")
            )
            if iv_change is not None and iv_change > 0.01:
                probabilities = {"VOL_UP": 0.54, "VOL_DOWN": 0.18, "NEUTRAL": 0.28}
            elif iv_change is not None and iv_change < -0.01:
                probabilities = {"VOL_UP": 0.18, "VOL_DOWN": 0.54, "NEUTRAL": 0.28}
            else:
                probabilities = {"VOL_UP": 0.20, "VOL_DOWN": 0.20, "NEUTRAL": 0.60}
        elif head_code == "option.exact_contract_net_profit":
            target_definition = (
                "Exact long-contract net profit from entry ask to regular exit bid, or final "
                "official settlement at expiry, after the frozen cost snapshot."
            )
            target_spec_version = "option.exact_contract_net_profit.v1"
            scoreability_rule = (
                "Entry ask and regular exit bid are mandatory; expiry uses only final official "
                "settlement with a frozen settlement-rule version and never rolls another contract."
            )
            scoreability_rule_version = "option.exact_contract_net_profit.scoreability.v1"
            labels = ["PROFIT", "LOSS"]
            if numeric_signal > threshold:
                probabilities = {"PROFIT": 0.58, "LOSS": 0.42}
            elif numeric_signal < -threshold:
                probabilities = {"PROFIT": 0.18, "LOSS": 0.82}
            else:
                probabilities = {"PROFIT": 0.50, "LOSS": 0.50}
        elif numeric_signal > threshold:
            labels = ["LONG", "SHORT", "NEUTRAL"]
            probabilities = {"LONG": 0.58, "SHORT": 0.18, "NEUTRAL": 0.24}
        elif numeric_signal < -threshold:
            labels = ["LONG", "SHORT", "NEUTRAL"]
            probabilities = {"LONG": 0.18, "SHORT": 0.58, "NEUTRAL": 0.24}
        else:
            labels = ["LONG", "SHORT", "NEUTRAL"]
            probabilities = {"LONG": 0.20, "SHORT": 0.20, "NEUTRAL": 0.60}
        model_revision = "v3" if self.asset_type == "option" else "v2"
        probability_model_version = f"{self.asset_type}-domain-shadow-rule-{model_revision}"
        artifact_hash = hashlib.sha256(probability_model_version.encode()).hexdigest()
        calibration_version = "not-promoted-v2"
        calibration_artifact_hash = hashlib.sha256(calibration_version.encode()).hexdigest()
        training_cutoff_at = snapshot.cutoff_at if snapshot is not None else datetime(1970, 1, 1)
        baseline_code = f"{self.asset_type}.neutral_baseline"
        baseline_version = "baseline-v1"
        head_hash = canonical_json_hash(
            {
                "head_code": head_code,
                "target_definition": target_definition,
                "target_spec_version": target_spec_version,
                "scoreability_rule": scoreability_rule,
                "scoreability_rule_version": scoreability_rule_version,
                "labels": labels,
                "probability_model_version": probability_model_version,
                "probability_artifact_hash": artifact_hash,
                "calibration_version": calibration_version,
                "calibration_artifact_hash": calibration_artifact_hash,
                "training_cutoff_at": training_cutoff_at.isoformat(),
                "baseline_code": baseline_code,
                "baseline_version": baseline_version,
            }
        )
        return PredictionHead(
            head_code=head_code,
            head_spec_hash=head_hash,
            target_definition=target_definition,
            target_spec_version=target_spec_version,
            scoreability_rule=scoreability_rule,
            scoreability_rule_version=scoreability_rule_version,
            labels=labels,
            probabilities=probabilities,
            probability_model_version=probability_model_version,
            probability_artifact_hash=artifact_hash,
            calibration_version=calibration_version,
            calibration_artifact_hash=calibration_artifact_hash,
            training_cutoff_at=training_cutoff_at,
            baseline_code=baseline_code,
            baseline_version=baseline_version,
            primary_for_promotion=primary_for_promotion,
        )

    def _required_capabilities(self, snapshot: RawAssetSnapshot) -> set[str]:
        del snapshot
        return {
            "bond": {"price", "official_valuation", "curve", "cashflows"},
            "fund": {"official_nav", "benchmark"},
            "futures": {"price", "contract_calendar"},
            "option": {"price", "option_chain", "contract_terms"},
            "fx": {"price", "calendar", "price_convention"},
            "crypto": {"price", "venue"},
        }[self.asset_type]

    def _asset_specific_quality_checks(
        self, snapshot: RawAssetSnapshot
    ) -> tuple[dict[str, bool | str | int | float | None], list[str]]:
        """Validate raw domain facts without coercing missing fields to zero.

        Source capabilities describe what a provider *can* supply; they are not
        evidence that the fact was actually supplied for this instrument and
        cutoff.  Keep the two gates separate so an incomplete snapshot is
        retained for audit but cannot become a generic momentum recommendation.
        """
        fields = snapshot.raw_fields
        quote = self._mapping(fields.get("snapshot"))
        reasons: list[str] = []
        checks: dict[str, bool | str | int | float | None] = {}

        if self.asset_type == "bond":
            bond = self._mapping(fields.get("bond"))
            identity_details = snapshot.identity.details
            is_perpetual = (
                bond.get("is_perpetual") is True
                or getattr(identity_details, "is_perpetual", None) is True
            )
            checks["bond_maturity_present"] = is_perpetual or self._present(
                bond.get("maturity_date")
            )
            checks["bond_cashflows_present"] = self._present(bond.get("cashflows"))
            checks["bond_curve_present"] = self._present(bond.get("curve"))
            checks["bond_benchmark_present"] = self._present(bond.get("benchmark"))
            checks["bond_valuation_present"] = self._present(
                quote.get("official_valuation")
            ) or self._present(bond.get("official_valuation"))
            if not checks["bond_maturity_present"]:
                reasons.append("BOND.MATURITY_MISSING")
            if not checks["bond_cashflows_present"]:
                reasons.append("BOND.CASHFLOWS_MISSING")
            if not checks["bond_curve_present"]:
                reasons.append("BOND.CURVE_MISSING")
            if not checks["bond_benchmark_present"]:
                reasons.append("COMMON.BENCHMARK_MISSING")
            if not checks["bond_valuation_present"]:
                reasons.append("COMMON.PRICE_UNAVAILABLE")
            if is_perpetual:
                reasons.append("BOND.PERPETUAL_MODEL_REQUIRED")
            has_executable_quote = self._valid_two_sided_quote(quote)
            checks["bond_executable_quote_present"] = has_executable_quote
            if checks["bond_valuation_present"] and not has_executable_quote:
                reasons.append("BOND.VALUATION_NOT_EXECUTABLE")
            if bond.get("evidence_coverage_low") is True:
                checks["bond_evidence_coverage_sufficient"] = False
                reasons.append("COMMON.EVIDENCE_COVERAGE_LOW")
            else:
                checks["bond_evidence_coverage_sufficient"] = (
                    None if bond.get("evidence_coverage_low") is None else True
                )
            if bond.get("peer_data_complete") is False:
                checks["bond_peer_data_complete"] = False
                reasons.append("BOND.PEER_DATA_INCOMPLETE")
            else:
                checks["bond_peer_data_complete"] = (
                    None if bond.get("peer_data_complete") is None else True
                )
            if bond.get("credit_disclosure_current") is False:
                checks["bond_credit_disclosure_current"] = False
                reasons.append("BOND.CREDIT_DISCLOSURE_STALE")
            else:
                checks["bond_credit_disclosure_current"] = (
                    None if bond.get("credit_disclosure_current") is None else True
                )
            return checks, reasons

        if self.asset_type == "fund":
            fund = self._mapping(fields.get("fund"))
            fund_type = str(fund.get("fund_type") or "").upper()
            checks["fund_type_present"] = bool(fund_type)
            checks["fund_official_nav_present"] = self._present(fund.get("official_nav"))
            checks["fund_benchmark_present"] = self._present(fund.get("benchmark"))
            checks["fund_fee_schedule_present"] = self._present(fund.get("fee_schedule"))
            checks["fund_holdings_as_of_present"] = self._present(fund.get("holdings_as_of"))
            if not checks["fund_type_present"]:
                reasons.append("FUND.TYPE_UNKNOWN")
            if not checks["fund_official_nav_present"]:
                reasons.append("FUND.OFFICIAL_NAV_MISSING")
            if not checks["fund_benchmark_present"]:
                reasons.append("COMMON.BENCHMARK_MISSING")
            if not checks["fund_fee_schedule_present"]:
                reasons.append("FUND.FEE_SCHEDULE_MISSING")
            if not checks["fund_holdings_as_of_present"]:
                reasons.append("FUND.HOLDINGS_AS_OF_MISSING")
            if fund.get("holdings_stale") is True:
                checks["fund_holdings_current"] = False
                reasons.append("FUND.HOLDINGS_STALE")
            else:
                checks["fund_holdings_current"] = (
                    None if fund.get("holdings_stale") is None else True
                )
            if fund.get("management_evidence_available") is False:
                checks["fund_management_evidence_available"] = False
                reasons.append("FUND.MANAGEMENT_EVIDENCE_LOW")
            else:
                checks["fund_management_evidence_available"] = (
                    None if fund.get("management_evidence_available") is None else True
                )
            if fund.get("secondary_market_data_complete") is False:
                checks["fund_secondary_market_data_complete"] = False
                reasons.append("FUND.SECONDARY_MARKET_DATA_PARTIAL")
            else:
                checks["fund_secondary_market_data_complete"] = (
                    None if fund.get("secondary_market_data_complete") is None else True
                )
            track_record_months = self._number(fund.get("track_record_months"))
            checks["fund_track_record_months"] = track_record_months
            if track_record_months is not None and track_record_months < 36:
                reasons.append("FUND.SHORT_TRACK_RECORD")
            return checks, reasons

        if self.asset_type == "futures":
            futures = self._mapping(fields.get("futures"))
            checks["futures_bid_ask_present"] = self._valid_two_sided_quote(quote)
            if not checks["futures_bid_ask_present"]:
                reasons.append("FUTURES.BID_ASK_MISSING")
            elif self._quote_crossed(quote):
                reasons.append("FUTURES.QUOTE_INCONSISTENT")
            optional_quality_flags = {
                "term_structure_complete": "FUTURES.TERM_STRUCTURE_INCOMPLETE",
                "basis_alignment_complete": "FUTURES.BASIS_ALIGNMENT_PARTIAL",
                "market_context_current": "FUTURES.MARKET_CONTEXT_STALE",
                "broker_margin_available": "FUTURES.BROKER_MARGIN_UNKNOWN",
                "fundamental_coverage_complete": "FUTURES.FUNDAMENTAL_COVERAGE_LOW",
            }
            for field_name, reason_code in optional_quality_flags.items():
                value = futures.get(field_name)
                checks[f"futures_{field_name}"] = None if value is None else value is True
                if value is False:
                    reasons.append(reason_code)
            return checks, reasons

        if self.asset_type == "option":
            option = self._mapping(fields.get("option"))
            details = snapshot.identity.details
            option_contract_id = str(getattr(details, "option_contract_id", "") or "")
            exchange = str(getattr(details, "exchange", "") or "")
            last_trade_at = getattr(details, "last_trade_at", None)
            expiry_at = getattr(details, "expiry_at", None)
            checks["option_identity_exact"] = (
                snapshot.identity.identity_level == "CONTRACT"
                and bool(option_contract_id)
                and option_contract_id.upper() == snapshot.identity.identifier_value.upper()
                and bool(exchange)
                and (
                    snapshot.identity.venue is None
                    or exchange.upper() == snapshot.identity.venue.upper()
                )
            )
            last_trade_at_present = (
                isinstance(last_trade_at, datetime) and last_trade_at.tzinfo is not None
            )
            checks["option_last_trade_at_present"] = last_trade_at_present
            checks["option_contract_tradeable"] = None
            if not checks["option_identity_exact"]:
                reasons.append("OPTION.CONTRACT_IDENTITY_MISMATCH")
            if not isinstance(last_trade_at, datetime) or last_trade_at.tzinfo is None:
                reasons.append("OPTION.CONTRACT_LAST_TRADE_MISSING")
            elif not isinstance(expiry_at, datetime) or expiry_at.tzinfo is None:
                reasons.append("OPTION.CONTRACT_IDENTITY_REQUIRED")
            else:
                cutoff_at = snapshot.cutoff_at
                if cutoff_at.tzinfo is None:
                    cutoff_at = cutoff_at.replace(tzinfo=last_trade_at.tzinfo)
                else:
                    cutoff_at = cutoff_at.astimezone(last_trade_at.tzinfo)
                checks["option_contract_tradeable"] = (
                    cutoff_at < last_trade_at and cutoff_at < expiry_at
                )
                if not checks["option_contract_tradeable"]:
                    reasons.append("OPTION.CONTRACT_NOT_TRADABLE")
            checks["option_contract_terms_present"] = self._present(option.get("contract_terms"))
            checks["option_bid_ask_present"] = self._valid_two_sided_quote(quote)
            pricing_input, pricing_input_reason = self._option_pricing_input(snapshot, option)
            checks["option_pricing_inputs_present"] = pricing_input is not None
            chain_records = option.get("chain")
            checks["option_chain_payload_present"] = isinstance(chain_records, list)
            chain_policy, chain_policy_reason = parse_option_chain_quality_policy(
                option.get("chain_quality_policy")
            )
            checks["option_chain_policy_present"] = chain_policy is not None
            cost_snapshot, cost_snapshot_reason = parse_option_cost_snapshot(
                option.get("cost_snapshot")
            )
            checks["option_cost_snapshot_present"] = cost_snapshot is not None
            underlying_quote_at = parse_option_chain_timestamp(option.get("underlying_quote_at"))
            checks["option_underlying_quote_timestamp_present"] = underlying_quote_at is not None
            option_quote_at = parse_option_chain_timestamp(quote.get("quote_at"))
            checks["option_quote_timestamp_present"] = option_quote_at is not None
            checks["option_quote_fresh"] = None
            checks["option_quote_synchronized"] = None
            if not checks["option_contract_terms_present"]:
                reasons.append("OPTION.CONTRACT_TERMS_MISSING")
            if not checks["option_bid_ask_present"]:
                reasons.append("OPTION.BID_ASK_MISSING")
            elif self._quote_crossed(quote):
                reasons.append("OPTION.QUOTE_INCONSISTENT")
            if pricing_input is None:
                reasons.append(pricing_input_reason or "OPTION.PRICING_INPUTS_MISSING")
            if not checks["option_chain_payload_present"]:
                reasons.append("OPTION.CHAIN_INCOMPLETE")
            if chain_policy is None:
                reasons.append(chain_policy_reason or "OPTION.CHAIN_POLICY_MISSING")
            if cost_snapshot is None:
                reasons.append(cost_snapshot_reason or "OPTION.COST_SNAPSHOT_MISSING")
            if underlying_quote_at is None:
                reasons.append("OPTION.CHAIN_UNDERLYING_TIMESTAMP_MISSING")
            if option_quote_at is None:
                reasons.append("OPTION.QUOTE_TIMESTAMP_MISSING")
            if (
                chain_policy is not None
                and underlying_quote_at is not None
                and option_quote_at is not None
            ):
                cutoff_at = snapshot.cutoff_at
                if cutoff_at.tzinfo is None:
                    cutoff_at = cutoff_at.replace(tzinfo=option_quote_at.tzinfo)
                else:
                    cutoff_at = cutoff_at.astimezone(option_quote_at.tzinfo)
                option_quote_age = (cutoff_at - option_quote_at).total_seconds()
                checks["option_quote_fresh"] = (
                    0 <= option_quote_age <= chain_policy.max_quote_age_seconds
                )
                checks["option_quote_synchronized"] = (
                    abs((option_quote_at - underlying_quote_at).total_seconds())
                    <= chain_policy.max_underlying_lag_seconds
                )
                if not checks["option_quote_fresh"]:
                    reasons.append("OPTION.QUOTE_STALE")
                if not checks["option_quote_synchronized"]:
                    reasons.append("OPTION.UNDERLYING_DESYNCHRONIZED")
            if (
                isinstance(chain_records, list)
                and chain_policy is not None
                and underlying_quote_at is not None
                and pricing_input is not None
            ):
                details = snapshot.identity.details
                expiry_at = getattr(details, "expiry_at", None)
                option_right = getattr(details, "option_right", None)
                strike = self._number(getattr(details, "strike", None))
                if (
                    not isinstance(expiry_at, datetime)
                    or option_right not in {"CALL", "PUT"}
                    or strike is None
                ):
                    reasons.append("OPTION.CONTRACT_IDENTITY_REQUIRED")
                else:
                    chain_quality = validate_option_chain(
                        records=chain_records,
                        pricing_template=pricing_input,
                        cutoff_at=snapshot.cutoff_at,
                        underlying_quote_at=underlying_quote_at,
                        target_expiry_at=expiry_at,
                        target_strike=strike,
                        target_right=option_right,
                        policy=chain_policy,
                    )
                    checks.update(chain_quality.checks)
                    reasons.extend(chain_quality.reason_codes)
            if (
                pricing_input is not None
                and checks["option_bid_ask_present"]
                and not self._quote_crossed(quote)
            ):
                bid_result = solve_implied_volatility(
                    replace(pricing_input, volatility=None),
                    observed_price=float(quote["bid"]),
                )
                ask_result = solve_implied_volatility(
                    replace(pricing_input, volatility=None),
                    observed_price=float(quote["ask"]),
                )
                checks["option_bid_iv_solved"] = bid_result.implied_volatility is not None
                checks["option_ask_iv_solved"] = ask_result.implied_volatility is not None
                checks["option_bid_iv_reason"] = bid_result.reason_code or ""
                checks["option_ask_iv_reason"] = ask_result.reason_code or ""
                if bid_result.implied_volatility is None or ask_result.implied_volatility is None:
                    reasons.append("OPTION.IV_SOLVER_FAILED")
            optional_quality_flags = {
                "surface_coverage_complete": "OPTION.SURFACE_COVERAGE_INSUFFICIENT",
                "liquidity_adequate": "OPTION.LIQUIDITY_DEGRADED",
                "secondary_pricing_inputs_current": "OPTION.SECONDARY_PRICING_INPUTS_STALE",
            }
            for field_name, reason_code in optional_quality_flags.items():
                value = option.get(field_name)
                checks[f"option_{field_name}"] = None if value is None else value is True
                if value is False:
                    reasons.append(reason_code)
            return checks, reasons

        if self.asset_type == "fx":
            fx = self._mapping(fields.get("fx"))
            reference_quote = (
                str(snapshot.source_manifest.get("quote_kind") or "").upper() == "REFERENCE"
            )
            checks["fx_bid_ask_present"] = self._valid_two_sided_quote(quote)
            checks["fx_reference_quote"] = reference_quote
            checks["fx_completed_bar"] = fx.get("completed_bar") is True
            checks["fx_price_convention_present"] = self._present(fx.get("price_convention"))
            if not checks["fx_bid_ask_present"]:
                if not reference_quote:
                    reasons.append("FX.BID_ASK_MISSING")
            elif self._quote_crossed(quote):
                reasons.append("FX.QUOTE_INCONSISTENT")
            if not checks["fx_completed_bar"]:
                reasons.append("FX.BAR_INCOMPLETE")
            if not checks["fx_price_convention_present"]:
                reasons.append("FX.PRICE_CONVENTION_UNKNOWN")
            optional_quality_flags = {
                "macro_available": "FX.MACRO_MISSING",
                "forward_points_available": "FX.FORWARD_POINTS_MISSING",
                "cot_available": "FX.COT_MISSING",
                "news_available": "FX.NEWS_COVERAGE_LOW",
                "history_sufficient": "FX.HISTORY_INSUFFICIENT",
            }
            for field_name, reason_code in optional_quality_flags.items():
                value = fx.get(field_name)
                checks[f"fx_{field_name}"] = None if value is None else value is True
                if value is False:
                    reasons.append(reason_code)
            if fx.get("cross_source_warning") is True:
                checks["fx_cross_source_warning"] = True
                reasons.append("FX.CROSS_SOURCE_WARNING")
            else:
                checks["fx_cross_source_warning"] = (
                    None if fx.get("cross_source_warning") is None else False
                )
            return checks, reasons

        crypto = self._mapping(fields.get("crypto"))
        market_quality_features = self._crypto_market_quality_feature_values(crypto)
        checks["crypto_bid_ask_present"] = self._valid_two_sided_quote(quote)
        checks["crypto_venue_verified"] = crypto.get("venue_verified") is True
        checks["crypto_depth_1pct_present"] = self._positive_number(
            market_quality_features.get("depth_1pct", crypto.get("depth_1pct"))
        )
        if not checks["crypto_bid_ask_present"]:
            reasons.append("CRYPTO.QUOTE_UNAVAILABLE")
        elif self._quote_crossed(quote):
            reasons.append("CRYPTO.QUOTE_INCONSISTENT")
        if not checks["crypto_venue_verified"]:
            reasons.append("CRYPTO.VENUE_UNVERIFIED")
        if not checks["crypto_depth_1pct_present"]:
            reasons.append("CRYPTO.DEPTH_INSUFFICIENT")
        venue_count = self._number(
            market_quality_features.get(
                "composite_price_venue_count", crypto.get("composite_price_venue_count")
            )
        )
        checks["crypto_composite_price_venue_count"] = venue_count
        if venue_count is not None and venue_count < 2:
            reasons.append("CRYPTO.SINGLE_VENUE_REFERENCE")
        market_quality_reason = market_quality_features.get("crypto_market_quality_reason_code")
        checks["crypto_market_quality_reason"] = market_quality_reason
        if isinstance(market_quality_reason, str) and market_quality_reason not in {
            "CRYPTO.SINGLE_VENUE_REFERENCE"
        }:
            reasons.append(market_quality_reason)
        optional_quality_flags = {
            "history_sufficient": "CRYPTO.HISTORY_INSUFFICIENT",
            "token_migration_complete": "CRYPTO.TOKEN_MIGRATION_INCOMPLETE",
            "onchain_provider_supported": "CRYPTO.ONCHAIN_UNSUPPORTED",
            "secondary_market_metrics_complete": "CRYPTO.SECONDARY_METRICS_MISSING",
        }
        for field_name, reason_code in optional_quality_flags.items():
            value = crypto.get(field_name)
            checks[f"crypto_{field_name}"] = None if value is None else value is True
            if value is False:
                reasons.append(reason_code)
        return checks, reasons

    @staticmethod
    def _mapping(value: object) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _present(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, Mapping)):
            return bool(value)
        return True

    @classmethod
    def _valid_two_sided_quote(cls, quote: Mapping[str, Any]) -> bool:
        return cls._positive_number(quote.get("bid")) and cls._positive_number(quote.get("ask"))

    @staticmethod
    def _positive_number(value: object) -> bool:
        if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
            return False
        try:
            return float(value) > 0
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _quote_crossed(quote: Mapping[str, Any]) -> bool:
        try:
            return float(quote["bid"]) > float(quote["ask"])
        except (KeyError, TypeError, ValueError):
            return False

    def _missing_capability_reason(self) -> str:
        return {
            "bond": "BOND.REQUIRED_SOURCE_CAPABILITY_MISSING",
            "fund": "FUND.REQUIRED_SOURCE_CAPABILITY_MISSING",
            "futures": "FUTURES.REQUIRED_SOURCE_CAPABILITY_MISSING",
            "option": "OPTION.CHAIN_INCOMPLETE",
            "fx": "FX.PRICE_CONVENTION_UNKNOWN",
            "crypto": "CRYPTO.VENUE_UNVERIFIED",
        }[self.asset_type]

    def _asset_feature_values(self, snapshot: RawAssetSnapshot) -> dict[str, float | str | None]:
        """Extract versioned domain inputs without making absent data equal zero."""
        fields = snapshot.raw_fields
        quote = self._mapping(fields.get("snapshot"))

        def number(container: Mapping[str, Any], *names: str) -> float | None:
            return self._first_number(*(container.get(name) for name in names))

        if self.asset_type == "bond":
            bond = self._mapping(fields.get("bond"))
            valuation_features = self._bond_analytics_feature_values(bond)
            return {
                "yield_to_maturity": valuation_features.get(
                    "yield_to_maturity", number(bond, "yield_to_maturity", "ytm")
                ),
                "yield_to_worst": number(bond, "yield_to_worst", "ytw"),
                "modified_duration": valuation_features.get(
                    "modified_duration", number(bond, "modified_duration", "duration")
                ),
                "dv01": valuation_features.get("dv01", number(bond, "dv01")),
                "convexity": valuation_features.get("convexity"),
                "clean_price": valuation_features.get("clean_price"),
                "dirty_price": valuation_features.get("dirty_price"),
                "accrued_interest": valuation_features.get("accrued_interest"),
                "bond_analytics_reason_code": valuation_features.get("bond_analytics_reason_code"),
                "credit_spread_bps": number(bond, "credit_spread_bps", "spread_bps"),
                "yield_change_bps": number(bond, "yield_change_bps", "ytm_change_bps"),
                "spread_change_bps": number(bond, "spread_change_bps"),
                "carry_return_20": number(bond, "carry_return_20", "carry_estimate"),
                "official_valuation": self._first_number(
                    quote.get("official_valuation"), bond.get("official_valuation")
                ),
            }
        if self.asset_type == "fund":
            fund = self._mapping(fields.get("fund"))
            metrics_features = self._fund_metrics_feature_values(fund)
            nav_return = self._number(
                metrics_features.get(
                    "fund_return_20",
                    number(fund, "official_nav_return_20", "nav_return_20", "return_20"),
                )
            )
            benchmark_return = self._number(
                metrics_features.get(
                    "benchmark_return_20",
                    number(fund, "benchmark_return_20", "benchmark_return"),
                )
            )
            explicit_excess = number(fund, "excess_return_20")
            return {
                "official_nav": number(fund, "official_nav", "nav"),
                "fund_return_20": nav_return,
                "benchmark_return_20": benchmark_return,
                "excess_return_20": metrics_features.get(
                    "excess_return_20",
                    explicit_excess
                    if explicit_excess is not None
                    else (
                        nav_return - benchmark_return
                        if nav_return is not None and benchmark_return is not None
                        else None
                    ),
                ),
                "expense_ratio": number(fund, "expense_ratio"),
                "tracking_error": metrics_features.get(
                    "tracking_error", number(fund, "tracking_error")
                ),
                "nav_premium_discount": metrics_features.get(
                    "nav_premium_discount", number(fund, "nav_premium_discount", "premium_discount")
                ),
                "fund_metrics_reason_code": metrics_features.get("fund_metrics_reason_code"),
                "style_drift_score": number(fund, "style_drift_score"),
            }
        if self.asset_type == "futures":
            futures = self._mapping(fields.get("futures"))
            term_structure_features = self._futures_term_structure_feature_values(futures)
            return {
                "basis": term_structure_features.get("basis", number(futures, "basis")),
                "basis_change": number(futures, "basis_change", "basis_return"),
                "annualized_carry": term_structure_features.get(
                    "annualized_carry", number(futures, "annualized_carry", "carry")
                ),
                "open_interest_change": number(futures, "open_interest_change"),
                "margin_ratio": number(futures, "margin_ratio"),
                "days_to_expiry": term_structure_features.get(
                    "days_to_expiry", number(futures, "days_to_expiry")
                ),
                "futures_term_structure_reason_code": term_structure_features.get(
                    "futures_term_structure_reason_code"
                ),
            }
        if self.asset_type == "option":
            option = self._mapping(fields.get("option"))
            analytics = self._option_analytics_feature_values(snapshot, option, quote)
            theoretical_value = self._number(analytics.get("theoretical_value"))
            market_price = self._number(analytics.get("market_price"))
            executable_entry_ask = self._number(quote.get("ask"))
            return {
                "underlying_return_20": number(
                    option, "underlying_return_20", "underlying_momentum_20"
                ),
                "implied_volatility": self._number(analytics.get("implied_volatility")),
                "implied_volatility_change": number(
                    option, "implied_volatility_change", "iv_change"
                ),
                "iv_rank": number(option, "iv_rank"),
                "market_price": market_price,
                "executable_entry_ask": executable_entry_ask,
                "contract_edge": (
                    theoretical_value / executable_entry_ask - 1.0
                    if theoretical_value is not None
                    and executable_entry_ask is not None
                    and executable_entry_ask != 0.0
                    else None
                ),
                **analytics,
            }
        if self.asset_type == "fx":
            fx = self._mapping(fields.get("fx"))
            return {
                "carry_estimate": number(fx, "carry_estimate", "carry"),
                "valuation_gap": number(fx, "valuation_gap", "fair_value_gap"),
                "rate_differential": number(fx, "rate_differential"),
                "macro_score": number(fx, "macro_score"),
            }
        crypto = self._mapping(fields.get("crypto"))
        market_quality_features = self._crypto_market_quality_feature_values(crypto)
        return {
            "funding_rate": number(crypto, "funding_rate"),
            "basis": number(crypto, "basis"),
            "open_interest_change": number(crypto, "open_interest_change"),
            "onchain_score": number(crypto, "onchain_score", "network_score"),
            "composite_mid": market_quality_features.get("composite_mid"),
            "depth_1pct": market_quality_features.get("depth_1pct", number(crypto, "depth_1pct")),
            "composite_price_venue_count": market_quality_features.get(
                "composite_price_venue_count", number(crypto, "composite_price_venue_count")
            ),
            "stablecoin_depeg_bps": market_quality_features.get("stablecoin_depeg_bps"),
            "crypto_market_quality_reason_code": market_quality_features.get(
                "crypto_market_quality_reason_code"
            ),
        }

    def _bond_analytics_feature_values(
        self, bond: Mapping[str, Any]
    ) -> dict[str, float | str | None]:
        """Calculate conventional bond metrics only from an explicit frozen input.

        Legacy feeds that publish precomputed metrics but no complete cashflow
        contract keep their existing raw values.  Once a collector supplies
        any fixed-rate valuation input, incomplete or unsolvable fields remain
        null with a named reason rather than falling back to a stale heuristic.
        """
        valuation_fields = (
            "settlement_date",
            "clean_price",
            "accrued_interest",
            "face_value",
            "coupon_frequency",
            "day_count",
            "cashflows",
        )
        if not any(field_name in bond for field_name in valuation_fields):
            return {}

        settlement_date = self._date(bond.get("settlement_date"))
        clean_price = self._decimal_number(bond.get("clean_price"))
        accrued_interest = self._decimal_number(bond.get("accrued_interest"))
        face_value = self._decimal_number(bond.get("face_value"))
        coupon_frequency = self._number(bond.get("coupon_frequency"))
        day_count = bond.get("day_count")
        if (
            settlement_date is None
            or clean_price is None
            or accrued_interest is None
            or face_value is None
            or coupon_frequency is None
            or int(coupon_frequency) != coupon_frequency
            or not isinstance(day_count, str)
            or not day_count.strip()
        ):
            return self._empty_bond_analytics_features("BOND.VALUATION_INPUTS_MISSING")

        raw_cashflows = bond.get("cashflows")
        if not isinstance(raw_cashflows, list):
            return self._empty_bond_analytics_features("BOND.CASHFLOW_INPUT_INVALID")
        cashflows: list[BondCashflow] = []
        for raw_cashflow in raw_cashflows:
            if not isinstance(raw_cashflow, Mapping):
                return self._empty_bond_analytics_features("BOND.CASHFLOW_INPUT_INVALID")
            payment_date = self._date(raw_cashflow.get("payment_date", raw_cashflow.get("date")))
            amount = self._decimal_number(raw_cashflow.get("amount"))
            if payment_date is None or amount is None:
                return self._empty_bond_analytics_features("BOND.CASHFLOW_INPUT_INVALID")
            cashflows.append(BondCashflow(payment_date=payment_date, amount=amount))

        analytics = calculate_fixed_rate_bond_analytics(
            BondValuationInput(
                settlement_date=settlement_date,
                clean_price=clean_price,
                accrued_interest=accrued_interest,
                face_value=face_value,
                coupon_frequency=int(coupon_frequency),
                day_count=day_count,
                cashflows=tuple(cashflows),
            )
        )
        return {
            "yield_to_maturity": self._number(analytics.yield_to_maturity),
            "modified_duration": self._number(analytics.modified_duration),
            "dv01": self._number(analytics.dv01),
            "convexity": self._number(analytics.convexity),
            "clean_price": self._number(analytics.clean_price),
            "dirty_price": self._number(analytics.dirty_price),
            "accrued_interest": self._number(analytics.accrued_interest),
            "bond_analytics_reason_code": analytics.reason_code,
        }

    def _fund_metrics_feature_values(
        self, fund: Mapping[str, Any]
    ) -> dict[str, float | str | None]:
        """Calculate NAV metrics only when the source supplied aligned series."""
        if "nav_series" not in fund and "benchmark_series" not in fund:
            return {}
        raw_nav_points = fund.get("nav_series")
        raw_benchmark_points = fund.get("benchmark_series")
        periods_per_year = self._number(fund.get("periods_per_year"))
        if (
            not isinstance(raw_nav_points, list)
            or not isinstance(raw_benchmark_points, list)
            or periods_per_year is None
            or int(periods_per_year) != periods_per_year
        ):
            return self._empty_fund_metrics_features("FUND.METRICS_INPUT_INVALID")

        nav_points: list[FundNavPoint] = []
        for raw_point in raw_nav_points:
            if not isinstance(raw_point, Mapping):
                return self._empty_fund_metrics_features("FUND.NAV_SERIES_INVALID")
            as_of = self._date(raw_point.get("as_of", raw_point.get("date")))
            nav = self._decimal_number(raw_point.get("nav"))
            distribution = self._decimal_number(raw_point.get("distribution", 0))
            if as_of is None or nav is None or distribution is None:
                return self._empty_fund_metrics_features("FUND.NAV_SERIES_INVALID")
            nav_points.append(FundNavPoint(as_of=as_of, nav=nav, distribution=distribution))

        benchmark_points: list[BenchmarkPoint] = []
        for raw_point in raw_benchmark_points:
            if not isinstance(raw_point, Mapping):
                return self._empty_fund_metrics_features("FUND.BENCHMARK_SERIES_INVALID")
            as_of = self._date(raw_point.get("as_of", raw_point.get("date")))
            level = self._decimal_number(raw_point.get("level"))
            if as_of is None or level is None:
                return self._empty_fund_metrics_features("FUND.BENCHMARK_SERIES_INVALID")
            benchmark_points.append(BenchmarkPoint(as_of=as_of, level=level))

        metrics = calculate_fund_metrics(
            FundMetricsInput(
                nav_points=tuple(nav_points),
                benchmark_points=tuple(benchmark_points),
                official_nav=self._decimal_number(fund.get("official_nav", fund.get("nav"))),
                market_mid=self._decimal_number(fund.get("market_mid")),
                periods_per_year=int(periods_per_year),
            )
        )
        return {
            "fund_return_20": self._number(metrics.nav_total_return),
            "benchmark_return_20": self._number(metrics.benchmark_total_return),
            "excess_return_20": self._number(metrics.excess_return),
            "tracking_error": self._number(metrics.tracking_error),
            "nav_premium_discount": self._number(metrics.premium_discount),
            "fund_metrics_reason_code": metrics.reason_code,
        }

    def _futures_term_structure_feature_values(
        self, futures: Mapping[str, Any]
    ) -> dict[str, float | str | None]:
        """Derive carry only from an explicit, comparable delivery specification."""
        raw_term_structure = futures.get("term_structure")
        if raw_term_structure is None:
            return {}
        if not isinstance(raw_term_structure, Mapping):
            return self._empty_futures_term_structure_features("FUTURES.TERM_STRUCTURE_INVALID")
        as_of = self._date(raw_term_structure.get("as_of"))
        expiry_date = self._date(raw_term_structure.get("expiry_date"))
        spot_price = self._decimal_number(raw_term_structure.get("spot_price"))
        futures_price = self._decimal_number(raw_term_structure.get("futures_price"))
        required_text = (
            "quote_unit",
            "spot_quality",
            "futures_quality",
            "spot_location",
            "futures_location",
            "tax_basis",
        )
        if (
            as_of is None
            or expiry_date is None
            or spot_price is None
            or futures_price is None
            or any(
                not isinstance(raw_term_structure.get(field_name), str)
                for field_name in required_text
            )
        ):
            return self._empty_futures_term_structure_features("FUTURES.TERM_STRUCTURE_INVALID")
        term_structure = calculate_futures_term_structure(
            FuturesTermStructureInput(
                as_of=as_of,
                expiry_date=expiry_date,
                spot_price=spot_price,
                futures_price=futures_price,
                quote_unit=str(raw_term_structure["quote_unit"]),
                spot_quality=str(raw_term_structure["spot_quality"]),
                futures_quality=str(raw_term_structure["futures_quality"]),
                spot_location=str(raw_term_structure["spot_location"]),
                futures_location=str(raw_term_structure["futures_location"]),
                tax_basis=str(raw_term_structure["tax_basis"]),
            )
        )
        return {
            "basis": self._number(term_structure.basis),
            "annualized_carry": self._number(term_structure.annualized_carry),
            "days_to_expiry": (
                float(term_structure.days_to_expiry)
                if term_structure.days_to_expiry is not None
                else None
            ),
            "futures_term_structure_reason_code": term_structure.reason_code,
        }

    def _crypto_market_quality_feature_values(
        self, crypto: Mapping[str, Any]
    ) -> dict[str, float | str | None]:
        """Build cross-venue facts only when a source supplied every venue quote."""
        raw_venue_quotes = crypto.get("venue_quotes")
        if raw_venue_quotes is None:
            return {}
        quote_asset = crypto.get("quote_asset")
        max_depeg_bps = self._number(crypto.get("max_stablecoin_depeg_bps"))
        if (
            not isinstance(raw_venue_quotes, list)
            or not isinstance(quote_asset, str)
            or not quote_asset.strip()
            or max_depeg_bps is None
            or int(max_depeg_bps) != max_depeg_bps
        ):
            return self._empty_crypto_market_quality_features("CRYPTO.MARKET_QUALITY_INPUT_INVALID")
        venue_quotes: list[CryptoVenueQuote] = []
        for raw_quote in raw_venue_quotes:
            if not isinstance(raw_quote, Mapping):
                return self._empty_crypto_market_quality_features(
                    "CRYPTO.MARKET_QUALITY_INPUT_INVALID"
                )
            venue = raw_quote.get("venue")
            bid = self._decimal_number(raw_quote.get("bid"))
            ask = self._decimal_number(raw_quote.get("ask"))
            depth = self._decimal_number(raw_quote.get("depth_1pct"))
            if not isinstance(venue, str) or bid is None or ask is None or depth is None:
                return self._empty_crypto_market_quality_features(
                    "CRYPTO.MARKET_QUALITY_INPUT_INVALID"
                )
            venue_quotes.append(CryptoVenueQuote(venue=venue, bid=bid, ask=ask, depth_1pct=depth))
        market_quality = calculate_crypto_market_quality(
            CryptoMarketQualityInput(
                quote_asset=quote_asset,
                venue_quotes=tuple(venue_quotes),
                stablecoin_usd_rate=self._decimal_number(crypto.get("stablecoin_usd_rate")),
                max_stablecoin_depeg_bps=int(max_depeg_bps),
            )
        )
        return {
            "composite_mid": self._number(market_quality.composite_mid),
            "depth_1pct": self._number(market_quality.total_depth_1pct),
            "composite_price_venue_count": (
                float(market_quality.venue_count)
                if market_quality.venue_count is not None
                else None
            ),
            "stablecoin_depeg_bps": self._number(market_quality.stablecoin_depeg_bps),
            "crypto_market_quality_reason_code": market_quality.reason_code,
        }

    @staticmethod
    def _empty_bond_analytics_features(reason_code: str) -> dict[str, float | str | None]:
        return {
            "yield_to_maturity": None,
            "modified_duration": None,
            "dv01": None,
            "convexity": None,
            "clean_price": None,
            "dirty_price": None,
            "accrued_interest": None,
            "bond_analytics_reason_code": reason_code,
        }

    @staticmethod
    def _empty_fund_metrics_features(reason_code: str) -> dict[str, float | str | None]:
        return {
            "fund_return_20": None,
            "benchmark_return_20": None,
            "excess_return_20": None,
            "tracking_error": None,
            "nav_premium_discount": None,
            "fund_metrics_reason_code": reason_code,
        }

    @staticmethod
    def _empty_futures_term_structure_features(reason_code: str) -> dict[str, float | str | None]:
        return {
            "basis": None,
            "annualized_carry": None,
            "days_to_expiry": None,
            "futures_term_structure_reason_code": reason_code,
        }

    @staticmethod
    def _empty_crypto_market_quality_features(reason_code: str) -> dict[str, float | str | None]:
        return {
            "composite_mid": None,
            "depth_1pct": None,
            "composite_price_venue_count": None,
            "stablecoin_depeg_bps": None,
            "crypto_market_quality_reason_code": reason_code,
        }

    def _option_analytics_feature_values(
        self,
        snapshot: RawAssetSnapshot,
        option: Mapping[str, Any],
        quote: Mapping[str, Any],
    ) -> dict[str, float | str | None]:
        """Derive reproducible option analytics from frozen contract inputs.

        Missing pricing inputs remain ``None`` with a named reason.  They are
        never substituted from a current quote, a different expiry or a zero
        rate/dividend assumption.
        """
        bid = self._number(quote.get("bid"))
        ask = self._number(quote.get("ask"))
        market_price = self._first_number(option.get("market_price"), quote.get("mid"))
        if market_price is None and bid is not None and ask is not None:
            market_price = (bid + ask) / 2.0
        if market_price is None:
            market_price = self._number(quote.get("price"))

        pricing_input, input_reason = self._option_pricing_input(snapshot, option)
        if pricing_input is None:
            return self._empty_option_analytics(
                model=None,
                market_price=market_price,
                reason_code=input_reason or "OPTION.PRICING_INPUTS_MISSING",
            )

        solver_input = replace(pricing_input, volatility=None)
        bid_solver = (
            solve_implied_volatility(solver_input, observed_price=bid) if bid is not None else None
        )
        ask_solver = (
            solve_implied_volatility(solver_input, observed_price=ask) if ask is not None else None
        )
        provider_volatility = self._first_number(option.get("implied_volatility"), option.get("iv"))
        market_solver = (
            solve_implied_volatility(solver_input, observed_price=market_price)
            if market_price is not None
            else None
        )
        volatility = provider_volatility
        reason_code: str | None = None
        if volatility is None and market_solver is not None:
            volatility = market_solver.implied_volatility
            reason_code = market_solver.reason_code
        if volatility is None:
            return self._empty_option_analytics(
                model=pricing_input.model,
                market_price=market_price,
                reason_code=reason_code or "OPTION.IMPLIED_VOLATILITY_MISSING",
                implied_volatility_bid=bid_solver.implied_volatility if bid_solver else None,
                implied_volatility_ask=ask_solver.implied_volatility if ask_solver else None,
            )

        analytics = calculate_option_analytics(replace(pricing_input, volatility=volatility))
        return {
            "pricing_model": pricing_input.model,
            "market_price": market_price,
            "theoretical_value": analytics.theoretical_value,
            "implied_volatility": volatility,
            "implied_volatility_bid": bid_solver.implied_volatility if bid_solver else None,
            "implied_volatility_ask": ask_solver.implied_volatility if ask_solver else None,
            "delta": analytics.delta,
            "gamma": analytics.gamma,
            "theta": analytics.theta,
            "vega": analytics.vega,
            "rho": analytics.rho,
            "break_even": analytics.break_even,
            "max_loss": analytics.max_loss,
            "price_lower_bound": analytics.price_lower_bound,
            "price_upper_bound": analytics.price_upper_bound,
            "pricing_reason_code": analytics.reason_code or reason_code,
        }

    def _option_pricing_input(
        self, snapshot: RawAssetSnapshot, option: Mapping[str, Any]
    ) -> tuple[OptionPricingInput | None, str | None]:
        """Delegate to the shared frozen-input builder used by outcome scoring."""
        del option
        return build_option_pricing_input(
            identity=snapshot.identity,
            cutoff_at=snapshot.cutoff_at,
            raw_fields=snapshot.raw_fields,
        )

    @staticmethod
    def _empty_option_analytics(
        *,
        model: str | None,
        market_price: float | None,
        reason_code: str,
        implied_volatility_bid: float | None = None,
        implied_volatility_ask: float | None = None,
    ) -> dict[str, float | str | None]:
        return {
            "pricing_model": model,
            "market_price": market_price,
            "theoretical_value": None,
            "implied_volatility": None,
            "implied_volatility_bid": implied_volatility_bid,
            "implied_volatility_ask": implied_volatility_ask,
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None,
            "break_even": None,
            "max_loss": None,
            "price_lower_bound": None,
            "price_upper_bound": None,
            "pricing_reason_code": reason_code,
        }

    def _domain_signal(
        self, features: FeatureSet, snapshot: RawAssetSnapshot
    ) -> tuple[float | None, int]:
        """Combine only named domain inputs into an uncalibrated shadow score."""
        values = features.values
        momentum = self._number(values.get("momentum_20"))

        def value(name: str) -> float | None:
            return self._number(values.get(name))

        components: list[float] = []
        if self.asset_type == "bond":
            if momentum is not None:
                components.append(0.35 * momentum)
            for name in ("yield_change_bps", "spread_change_bps"):
                if (change_bps := value(name)) is not None:
                    components.append(-change_bps / 10_000)
            if (carry := value("carry_return_20")) is not None:
                components.append(carry)
        elif self.asset_type == "fund":
            excess_return = value("excess_return_20")
            if excess_return is not None:
                components.append(excess_return)
            elif momentum is not None:
                # Official NAV is a quality prerequisite, so this remains a
                # NAV-based fallback rather than a stock-price proxy.
                components.append(0.60 * momentum)
            if (premium := value("nav_premium_discount")) is not None:
                components.append(-0.20 * premium)
            if (style_drift := value("style_drift_score")) is not None:
                components.append(-0.05 * abs(style_drift))
        elif self.asset_type == "futures":
            if momentum is not None:
                components.append(0.75 * momentum)
            if (carry := value("annualized_carry")) is not None:
                components.append(0.25 * carry * 20 / 252)
            if (basis_change := value("basis_change")) is not None:
                components.append(0.20 * basis_change)
        elif self.asset_type == "option":
            option_right = str(getattr(snapshot.identity.details, "option_right", "")).upper()
            if (underlying_return := value("underlying_return_20")) is not None:
                components.append(
                    underlying_return if option_right == "CALL" else -underlying_return
                )
            if (edge := value("contract_edge")) is not None:
                components.append(0.50 * edge)
        elif self.asset_type == "fx":
            if momentum is not None:
                components.append(0.70 * momentum)
            if (carry := value("carry_estimate")) is not None:
                components.append(0.30 * carry * 20 / 252)
            if (valuation_gap := value("valuation_gap")) is not None:
                components.append(0.20 * valuation_gap)
            if (macro_score := value("macro_score")) is not None:
                components.append(0.01 * macro_score)
        else:
            if momentum is not None:
                components.append(0.70 * momentum)
            if (funding_rate := value("funding_rate")) is not None:
                components.append(-3 * funding_rate)
            if (basis := value("basis")) is not None:
                components.append(-0.20 * basis)
            if (onchain_score := value("onchain_score")) is not None:
                components.append(0.01 * onchain_score)

        finite = [component for component in components if math.isfinite(component)]
        return (sum(finite) if finite else None, len(finite))

    def _signal_threshold(self) -> float:
        return {
            "bond": 0.005,
            "fund": 0.010,
            "futures": 0.015,
            "option": 0.030,
            "fx": 0.010,
            "crypto": 0.025,
        }[self.asset_type]

    @staticmethod
    def _shadow_confidence(score: float | None, threshold: float) -> float | None:
        if score is None or threshold <= 0:
            return None
        strength = min(abs(score) / threshold, 1.0)
        return min(0.65, 0.50 + 0.15 * strength)

    def _horizon_spec(self, snapshot: RawAssetSnapshot | None) -> HorizonSpec:
        unit = {
            "bond": "BOND_SESSION",
            "fund": "FUND_VALUATION_DAY",
            "futures": "TRADING_SESSION",
            "option": "TRADING_SESSION",
            "fx": "FX_SESSION",
            "crypto": "CALENDAR_DAY",
        }[self.asset_type]
        details = snapshot.identity.details if snapshot is not None else None
        calendar_id = {
            "bond": getattr(details, "settlement_calendar_id", None) or "BOND_DEFAULT",
            "fund": getattr(details, "nav_calendar_id", None) or "FUND_DEFAULT",
            "futures": getattr(details, "trading_calendar_id", None) or "FUTURES_DEFAULT",
            "option": getattr(details, "trading_calendar_id", None) or "OPTION_DEFAULT",
            "fx": getattr(details, "calendar_id", None) or "FX_DEFAULT",
            "crypto": "UTC",
        }[self.asset_type]
        return HorizonSpec(count=20, unit=unit, calendar_id=calendar_id)

    def _asset_details(self, snapshot: RawAssetSnapshot, features: FeatureSet | None) -> Any:
        values = features.values if features else {}
        quote = self._mapping(snapshot.raw_fields.get("snapshot"))
        if self.asset_type == "bond":
            bond = self._mapping(snapshot.raw_fields.get("bond"))
            price_basis = (
                "EXECUTABLE"
                if self._valid_two_sided_quote(quote)
                else (
                    "OFFICIAL_VALUATION"
                    if self._first_number(
                        quote.get("official_valuation"), bond.get("official_valuation")
                    )
                    is not None
                    else "INDICATIVE"
                )
            )
            return BondResearchDetails(
                price_basis=price_basis,
                clean_price=self._number(values.get("clean_price")),
                accrued_interest=self._number(values.get("accrued_interest")),
                dirty_price=self._number(values.get("dirty_price")),
                yield_to_maturity=self._number(values.get("yield_to_maturity")),
                yield_to_worst=self._number(values.get("yield_to_worst")),
                modified_duration=self._number(values.get("modified_duration")),
                convexity=self._number(values.get("convexity")),
                dv01=self._number(values.get("dv01")),
                credit_spread_bps=self._number(values.get("credit_spread_bps")),
                valuation_reason_code=(
                    str(values.get("bond_analytics_reason_code"))
                    if values.get("bond_analytics_reason_code") is not None
                    else None
                ),
                liquidity_grade=self._enum(
                    bond.get("liquidity_grade"), {"HIGH", "MEDIUM", "LOW"}, "UNKNOWN"
                ),
            )
        if self.asset_type == "fund":
            fund = self._mapping(snapshot.raw_fields.get("fund"))
            fund_type = self._enum(
                fund.get("fund_type"),
                {"ETF", "LOF", "OPEN_END", "MONEY_MARKET", "OTHER"},
                "OTHER",
            )
            return FundResearchDetails(
                fund_type=fund_type,
                benchmark_code=str(fund.get("benchmark") or "") or None,
                nav_total_return=self._number(values.get("fund_return_20")),
                benchmark_total_return=self._number(values.get("benchmark_return_20")),
                excess_return=self._number(values.get("excess_return_20")),
                expense_ratio=self._number(values.get("expense_ratio")),
                tracking_error=self._number(values.get("tracking_error")),
                nav_premium_discount=self._number(values.get("nav_premium_discount")),
                style_drift_score=self._number(values.get("style_drift_score")),
                metrics_reason_code=(
                    str(values.get("fund_metrics_reason_code"))
                    if values.get("fund_metrics_reason_code") is not None
                    else None
                ),
                liquidity_grade=self._enum(
                    fund.get("liquidity_grade"),
                    {"HIGH", "MEDIUM", "LOW", "NOT_APPLICABLE"},
                    "UNKNOWN",
                ),
            )
        if self.asset_type == "futures":
            futures = self._mapping(snapshot.raw_fields.get("futures"))
            expiry_at = getattr(snapshot.identity.details, "expiry_at", None)
            days_to_expiry = self._number(values.get("days_to_expiry"))
            if days_to_expiry is None and isinstance(expiry_at, datetime):
                days_to_expiry = max((expiry_at.date() - snapshot.cutoff_at.date()).days, 0)
            roll_state = self._enum(
                futures.get("roll_state"), {"NORMAL", "ROLL_WINDOW", "NEAR_EXPIRY"}, "UNKNOWN"
            )
            if roll_state == "UNKNOWN" and days_to_expiry is not None:
                roll_state = "NEAR_EXPIRY" if days_to_expiry <= 5 else "NORMAL"
            return FuturesResearchDetails(
                contract_code=snapshot.identity.display_symbol,
                mapped_from_series=bool(
                    getattr(snapshot.identity.details, "mapped_contract_id", None)
                ),
                days_to_expiry=int(days_to_expiry) if days_to_expiry is not None else None,
                basis=self._number(values.get("basis")),
                annualized_carry=self._number(values.get("annualized_carry")),
                roll_state=roll_state,
                margin_ratio=self._number(values.get("margin_ratio")),
                term_structure_reason_code=(
                    str(values.get("futures_term_structure_reason_code"))
                    if values.get("futures_term_structure_reason_code") is not None
                    else None
                ),
            )
        if self.asset_type == "option":
            underlying_return = self._number(values.get("underlying_return_20"))
            iv_change = self._number(values.get("implied_volatility_change"))
            edge = self._number(values.get("contract_edge"))
            return OptionResearchDetails(
                underlying_view=(
                    "BULLISH"
                    if underlying_return is not None and underlying_return > 0.01
                    else (
                        "BEARISH"
                        if underlying_return is not None and underlying_return < -0.01
                        else "INDETERMINATE"
                    )
                ),
                volatility_view=(
                    "VOL_UP"
                    if iv_change is not None and iv_change > 0.01
                    else (
                        "VOL_DOWN"
                        if iv_change is not None and iv_change < -0.01
                        else "INDETERMINATE"
                    )
                ),
                contract_edge=(
                    "CHEAP"
                    if edge is not None and edge > 0.03
                    else "RICH"
                    if edge is not None and edge < -0.03
                    else "UNKNOWN"
                ),
                pricing_model=(
                    str(values.get("pricing_model"))
                    if values.get("pricing_model") in {"BSM", "BLACK_76", "AMERICAN_BINOMIAL"}
                    else None
                ),
                market_price=self._number(values.get("market_price")),
                theoretical_value=self._number(values.get("theoretical_value")),
                implied_volatility=self._number(values.get("implied_volatility")),
                implied_volatility_bid=self._number(values.get("implied_volatility_bid")),
                implied_volatility_ask=self._number(values.get("implied_volatility_ask")),
                delta=self._number(values.get("delta")),
                gamma=self._number(values.get("gamma")),
                theta=self._number(values.get("theta")),
                vega=self._number(values.get("vega")),
                rho=self._number(values.get("rho")),
                break_even=self._number(values.get("break_even")),
                max_loss=self._number(values.get("max_loss")),
                pricing_reason_code=(
                    str(values.get("pricing_reason_code"))
                    if values.get("pricing_reason_code") is not None
                    else None
                ),
            )
        if self.asset_type == "fx":
            details = snapshot.identity.details
            base = details.base_currency if isinstance(details, FxIdentityDetails) else "UNKNOWN"
            quote_currency = (
                details.quote_currency if isinstance(details, FxIdentityDetails) else "UNKNOWN"
            )
            settlement_type = (
                details.settlement_type if isinstance(details, FxIdentityDetails) else None
            )
            fx = self._mapping(snapshot.raw_fields.get("fx"))
            quote_kind = (
                "REFERENCE"
                if str(snapshot.source_manifest.get("quote_kind") or "").upper() == "REFERENCE"
                else "EXECUTABLE_PROXY"
                if self._valid_two_sided_quote(self._mapping(snapshot.raw_fields.get("snapshot")))
                else "INDICATIVE"
            )
            return FxResearchDetails(
                base_currency=base,
                quote_currency=quote_currency,
                product_type=self._enum(settlement_type, {"SPOT", "FORWARD", "NDF"}, "SPOT"),
                quote_kind=quote_kind,
                carry_estimate=self._number(values.get("carry_estimate")),
                valuation_gap=self._number(values.get("valuation_gap")),
                liquidity_grade=self._enum(
                    fx.get("liquidity_grade"), {"MAJOR", "MINOR", "EMERGING"}, "UNKNOWN"
                ),
            )
        crypto = self._mapping(snapshot.raw_fields.get("crypto"))
        product_type = self._enum(
            getattr(snapshot.identity.details, "market_type", None),
            {"ASSET", "SPOT", "PERPETUAL", "DELIVERY_FUTURE"},
            "SPOT",
        )
        return CryptoResearchDetails(
            network=str(crypto.get("network") or "") or None,
            venue=snapshot.identity.venue,
            product_type=product_type,
            quote_currency=snapshot.identity.currency,
            composite_mid=self._number(values.get("composite_mid")),
            composite_price_venue_count=(
                int(venue_count)
                if (venue_count := self._number(values.get("composite_price_venue_count")))
                is not None
                else None
            ),
            depth_1pct=self._number(values.get("depth_1pct")),
            stablecoin_depeg_bps=self._number(values.get("stablecoin_depeg_bps")),
            funding_rate=self._number(values.get("funding_rate")),
            basis=self._number(values.get("basis")),
            onchain_regime=self._enum(
                crypto.get("onchain_regime"), {"EXPANDING", "CONTRACTING", "MIXED"}, "UNAVAILABLE"
            ),
            venue_risk_grade=self._enum(
                crypto.get("venue_risk_grade"), {"LOW", "MEDIUM", "HIGH"}, "UNKNOWN"
            ),
            market_quality_reason_code=(
                str(values.get("crypto_market_quality_reason_code"))
                if values.get("crypto_market_quality_reason_code") is not None
                else None
            ),
        )

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @classmethod
    def _decimal_number(cls, value: object) -> Decimal | None:
        number = cls._number(value)
        return Decimal(str(number)) if number is not None else None

    @staticmethod
    def _date(value: object) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    @classmethod
    def _first_number(cls, *values: object) -> float | None:
        for value in values:
            if (number := cls._number(value)) is not None:
                return number
        return None

    @staticmethod
    def _enum(value: object, allowed: set[str], default: str) -> str:
        candidate = str(value or "").upper()
        return candidate if candidate in allowed else default

    @staticmethod
    def _closing_prices(snapshot: RawAssetSnapshot) -> list[float]:
        prices: list[float] = []
        for row in snapshot.history_rows:
            raw = row.get("close", row.get("price"))
            try:
                if raw is not None:
                    prices.append(float(raw))
            except (TypeError, ValueError):
                continue
        snapshot_price = (snapshot.raw_fields.get("snapshot") or {}).get("price")
        if not prices and snapshot_price is not None:
            try:
                prices.append(float(snapshot_price))
            except (TypeError, ValueError):
                pass
        return prices

    @staticmethod
    def _volatility(prices: list[float]) -> float | None:
        if len(prices) < 3:
            return None
        returns = [
            prices[index] / prices[index - 1] - 1
            for index in range(1, len(prices))
            if prices[index - 1]
        ]
        if len(returns) < 2:
            return None
        mean = fmean(returns)
        return (sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)) ** 0.5
