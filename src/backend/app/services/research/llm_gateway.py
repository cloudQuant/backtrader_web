"""The sole provenance-recording boundary for protocol-v2 model invocations."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.db import database
from app.models.ai_research_v2 import ResearchModelInvocation, ResearchRun
from app.services.research.canonical import content_hash
from app.services.research.capability_registry import CapabilityRegistry
from app.services.research.database_clock import database_utc_now
from app.services.research.model_budget import BudgetQuote, ModelAccountingPolicy, quote_request
from app.services.research.provider_contract import PreparedProviderRequest
from app.services.research.quota import (
    QuotaConflictError,
    QuotaDispatchRequirement,
    QuotaReservationReceipt,
    QuotaService,
    QuotaSettlementRequest,
)
from app.services.research.redaction import redact_sensitive_payload


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Already-redacted, typed provider payload passed through the gateway."""

    resolved_model: str
    prompt_template_version: str
    system_input: dict[str, Any]
    typed_input: dict[str, Any]
    sampling_params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Normalized provider result that can be recorded without provider coupling."""

    output: str
    provider_request_id: str | None
    token_usage: Mapping[str, Any]
    cost: Mapping[str, Any]
    fallback_chain: tuple[str, ...] = ()
    observed_model: str | None = None


@dataclass(frozen=True, slots=True)
class GatewayResult:
    """Safe result plus immutable model-invocation identity."""

    invocation_id: str
    requested_model: str
    resolved_model: str
    output: str


class ModelProvider(Protocol):
    """Provider adapter owned by infrastructure, not feature code."""

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate a response from an already-redacted typed request."""

    def prepare(self, request: ProviderRequest) -> PreparedProviderRequest:
        """Seal the exact bytes without external IO for budgeted deployments."""

    async def generate_prepared(self, prepared: PreparedProviderRequest) -> ProviderResponse:
        """Send precisely the bytes admitted by the joint budget boundary."""


class ModelCatalog:
    """Server-owned aliases; each resolution is retained in the invocation ledger."""

    def __init__(self, aliases: Mapping[str, str]) -> None:
        self._aliases = dict(aliases)

    def resolve(self, requested_model: str) -> str:
        """Resolve one configured alias or reject implicit provider defaults."""

        resolved = self._aliases.get(requested_model)
        if not resolved:
            raise ValueError("LLM_MODEL_ALIAS_NOT_FOUND")
        return resolved

    def set_alias(self, requested_model: str, resolved_model: str) -> None:
        """Update a server-owned alias for later invocations only."""

        if not requested_model.strip() or not resolved_model.strip():
            raise ValueError("LLM_MODEL_ALIAS_INVALID")
        self._aliases[requested_model] = resolved_model


class LlmGateway:
    """Invoke models through a quota-fenced, redacted provenance ledger."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        catalog: ModelCatalog,
        provider_identity: str = "gateway_provider",
        require_model_identity: bool = False,
        accounting_policy: ModelAccountingPolicy | None = None,
        dispatch_timeout_seconds: float = 60.0,
    ) -> None:
        if (
            not provider_identity
            or _response_text(provider_identity, 128, "LLM_PROVIDER_IDENTITY_INVALID")
            != provider_identity
            or type(require_model_identity) is not bool
        ):
            raise ValueError("LLM_PROVIDER_IDENTITY_INVALID")
        self._provider = provider
        self._catalog = catalog
        self._provider_identity = provider_identity
        self._require_model_identity = require_model_identity
        if accounting_policy is not None and (
            not isinstance(accounting_policy, ModelAccountingPolicy)
            or not require_model_identity
            or not callable(getattr(provider, "prepare", None))
            or not callable(getattr(provider, "generate_prepared", None))
            or type(dispatch_timeout_seconds) not in {int, float}
            or not math.isfinite(dispatch_timeout_seconds)
            or not 0 < dispatch_timeout_seconds <= 600
        ):
            raise ValueError("LLM_ACCOUNTING_CONFIGURATION_INVALID")
        self._accounting_policy = accounting_policy
        self._dispatch_timeout_seconds = dispatch_timeout_seconds
        self._quota = QuotaService()

    @property
    def requires_budget_bundle(self) -> bool:
        """Real generation factories require this; legacy injected seams may not."""

        return self._accounting_policy is not None

    async def prepare_budget(
        self,
        *,
        run_id: str,
        requested_model: str,
        prompt_template_version: str,
        system_input: Mapping[str, Any],
        typed_input: Mapping[str, Any],
        sampling_params: Mapping[str, Any],
        token_limit: int,
    ) -> BudgetQuote:
        """Redact and seal the exact input before reserving either budget."""

        if self._accounting_policy is None:
            raise ValueError("LLM_ACCOUNTING_POLICY_REQUIRED")
        await self._validated_run(run_id)
        request = ProviderRequest(
            self._catalog.resolve(requested_model),
            prompt_template_version,
            _safe_mapping(system_input),
            _safe_mapping(typed_input),
            _safe_sampling_mapping(sampling_params),
        )
        prepared = self._provider.prepare(request)
        if prepared.provider_id != self._provider_identity:
            raise ValueError("LLM_BUDGET_REQUEST_MISMATCH")
        async with database.async_session_maker() as session:
            now = await database_utc_now(session)
        return quote_request(
            prepared,
            self._accounting_policy,
            token_limit=token_limit,
            now=now,
            dispatch_timeout_seconds=self._dispatch_timeout_seconds,
        )

    async def invoke(
        self,
        *,
        run_id: str,
        requested_model: str,
        prompt_template_version: str,
        system_input: Mapping[str, Any],
        typed_input: Mapping[str, Any],
        sampling_params: Mapping[str, Any],
        task_id: str,
        stage_attempt_id: str,
        lease_token: str,
        stage: str,
        quota_reservation_id: str,
        quota_fencing_token: int,
        origin: str = "LLM",
        tool_manifest: tuple[str, ...] = (),
        budget_quote: BudgetQuote | None = None,
        quota_receipts: tuple[QuotaReservationReceipt, ...] = (),
        quota_policy_version: str | None = None,
    ) -> GatewayResult:
        """Run a single fenced call and append its complete model lineage."""

        if origin not in {"LLM", "RAG", "REPAIR", "FALLBACK", "TEMPLATE"}:
            raise ValueError("LLM_ORIGIN_INVALID")
        if not prompt_template_version.strip():
            raise ValueError("LLM_PROMPT_TEMPLATE_VERSION_REQUIRED")
        run = await self._validated_run(run_id)
        if not await self._quota.validate_stage_attempt_fencing(
            quota_reservation_id,
            quota_fencing_token,
            task_id=task_id,
            run_id=run.id,
            stage_attempt_id=stage_attempt_id,
            lease_token=lease_token,
            stage=stage,
        ):
            raise ValueError("LLM_STAGE_ATTEMPT_FENCING_DENIED")
        resolved_model = self._catalog.resolve(requested_model)
        safe_system = _safe_mapping(system_input)
        safe_input = _safe_mapping(typed_input)
        safe_sampling = _safe_sampling_mapping(sampling_params)
        provider_request = ProviderRequest(
            resolved_model=resolved_model,
            prompt_template_version=prompt_template_version,
            system_input=safe_system,
            typed_input=safe_input,
            sampling_params=safe_sampling,
        )
        operation_id = f"llm:{quota_reservation_id}:{quota_fencing_token}"
        budget_cost: dict[str, Any] = {}
        if self.requires_budget_bundle:
            if (
                not isinstance(budget_quote, BudgetQuote)
                or tool_manifest
                or (not isinstance(quota_policy_version, str) or not quota_policy_version)
            ):
                raise ValueError("LLM_BUDGET_BUNDLE_REQUIRED")
            if self._provider.prepare(provider_request) != budget_quote.prepared:
                raise ValueError("LLM_BUDGET_REQUEST_MISMATCH")
            await self._revalidate_quote(budget_quote)
            quote_context = budget_quote.context(
                run_request_hash=run.request_hash,
                task_id=task_id,
                stage_attempt_id=stage_attempt_id,
                quota_policy_version=quota_policy_version,
            )
            quote_hash = content_hash(quote_context)
            expected = {
                "model_tokens": ("tokens", budget_quote.reserved_tokens),
                "model_cost_microusd": ("microusd", budget_quote.reserved_microusd),
            }
            if (
                type(quota_receipts) is not tuple
                or len(quota_receipts) != 2
                or any(not isinstance(item, QuotaReservationReceipt) for item in quota_receipts)
                or {item.resource_type for item in quota_receipts} != set(expected)
                or any(
                    (item.unit, item.reserved_amount) != expected[item.resource_type]
                    for item in quota_receipts
                )
                or not any(
                    item.resource_type == "model_tokens"
                    and item.reservation_id == quota_reservation_id
                    and item.fencing_token == quota_fencing_token
                    for item in quota_receipts
                )
            ):
                raise ValueError("LLM_BUDGET_BUNDLE_REQUIRED")
            claimed = await self._quota.claim_external_dispatch_bundle(
                tuple(
                    QuotaDispatchRequirement(
                        reservation_id=item.reservation_id,
                        fencing_token=item.fencing_token,
                        resource_type=item.resource_type,
                        unit=item.unit,
                        reserved_amount=item.reserved_amount,
                        request_hash=quote_hash,
                        require_reservation_context=True,
                    )
                    for item in quota_receipts
                ),
                provider_operation_id=operation_id,
                task_id=task_id,
                run_id=run.id,
                stage_attempt_id=stage_attempt_id,
                lease_token=lease_token,
                stage=stage,
            )
            budget_cost = {
                "accounting_basis": "UNRESOLVED",
                "quote_hash": quote_hash,
                "policy_hash": budget_quote.policy.content_hash,
                "reservation_ids": [item.reservation_id for item in quota_receipts],
            }
        else:
            if budget_quote is not None or quota_receipts:
                raise ValueError("LLM_ACCOUNTING_POLICY_REQUIRED")
            claimed = await self._quota.claim_external_dispatch(
                quota_reservation_id,
                quota_fencing_token,
                provider_operation_id=operation_id,
                task_id=task_id,
                run_id=run.id,
                stage_attempt_id=stage_attempt_id,
                lease_token=lease_token,
                stage=stage,
                resource_type="model_tokens",
                unit="tokens",
            )
        if not claimed:
            raise ValueError("LLM_DISPATCH_ALREADY_CLAIMED")

        system_hash = content_hash(safe_system)
        input_hash = content_hash({"system": safe_system, "input": safe_input})
        try:
            if budget_quote is not None:
                # A delayed database claim must not dispatch an expired tariff.
                await self._revalidate_quote(budget_quote)
                response = await self._provider.generate_prepared(budget_quote.prepared)
            else:
                response = await self._provider.generate(provider_request)
        except Exception:
            await self._record_invocation(
                run_id=run.id,
                requested_model=requested_model,
                resolved_model=resolved_model,
                prompt_template_version=prompt_template_version,
                system_input_hash=system_hash,
                input_hash=input_hash,
                sampling_params=safe_sampling,
                tool_manifest=tool_manifest,
                origin=origin,
                fallback_chain=(),
                token_usage={},
                cost=budget_cost,
                output=None,
                provider_request_id=None,
                error_code="LLM_PROVIDER_FAILED",
            )
            raise
        error_code = None
        try:
            response = _validated_provider_response(response)
            safe_output: str | None = response.output
        except ValueError as exc:
            # Adapter type annotations are not runtime validation. Never let
            # malformed metadata fail serialization after quota settlement,
            # or retain arbitrary response values in the failure receipt.
            error_code = str(exc)
            response = ProviderResponse("", None, {}, {})
            safe_output = None
        # A provider response is not a completed quota lifecycle. Only a
        # verified nonnegative integral token count can settle this resource;
        # missing/ambiguous usage remains reserved for explicit readback.
        settled_amount = _verified_token_count(response.token_usage)
        if error_code is None and self._require_model_identity:
            if response.observed_model is None:
                error_code = "LLM_PROVIDER_MODEL_UNVERIFIED"
            elif response.observed_model != resolved_model:
                error_code = "LLM_PROVIDER_MODEL_MISMATCH"
        if error_code is not None:
            pass  # Preserve the reservation until an explicit provider readback.
        elif settled_amount is None:
            error_code = "LLM_PROVIDER_USAGE_UNVERIFIED"
        else:
            try:
                if budget_quote is not None:
                    components = _verified_token_components(response.token_usage)
                    if components is None:
                        raise ValueError("LLM_PROVIDER_USAGE_UNVERIFIED")
                    try:
                        token_amount, money_amount = budget_quote.settlement(
                            input_tokens=components[0], output_tokens=components[1]
                        )
                    except ValueError:
                        raise ValueError("LLM_PROVIDER_USAGE_OUTSIDE_BUDGET") from None
                    amounts = {"model_tokens": token_amount, "model_cost_microusd": money_amount}
                    settled = await self._quota.settle_bundle(
                        tuple(
                            QuotaSettlementRequest(
                                reservation_id=item.reservation_id,
                                fencing_token=item.fencing_token,
                                settled_amount=amounts[item.resource_type],
                            )
                            for item in quota_receipts
                        ),
                        provider_operation_id=operation_id,
                    )
                    if settled:
                        budget_cost = {
                            **budget_cost,
                            "accounting_basis": "CONSERVATIVE_TARIFF_BOUND",
                            "currency": "USD",
                            "amount_microusd": money_amount,
                        }
                else:
                    settled = await self._quota.settle(
                        quota_reservation_id,
                        quota_fencing_token,
                        settled_amount=settled_amount,
                    )
            except QuotaConflictError:
                settled = False
            except ValueError as exc:
                settled = False
                error_code = str(exc)
            if not settled and error_code is None:
                error_code = "LLM_QUOTA_SETTLEMENT_FAILED"
        invocation = await self._record_invocation(
            run_id=run.id,
            requested_model=requested_model,
            resolved_model=resolved_model,
            prompt_template_version=prompt_template_version,
            system_input_hash=system_hash,
            input_hash=input_hash,
            sampling_params=safe_sampling,
            tool_manifest=tool_manifest,
            origin=origin,
            fallback_chain=response.fallback_chain,
            token_usage=dict(response.token_usage),
            cost=budget_cost if budget_quote is not None else dict(response.cost),
            output=safe_output,
            provider_request_id=response.provider_request_id,
            error_code=error_code,
            provider_reported_model=response.observed_model,
        )
        if error_code is not None:
            raise ValueError(error_code)
        assert safe_output is not None
        return GatewayResult(
            invocation_id=invocation.id,
            requested_model=requested_model,
            resolved_model=resolved_model,
            output=safe_output,
        )

    async def _revalidate_quote(self, quote: BudgetQuote) -> None:
        """Recheck the bound policy, exact ceilings and database-time validity."""

        if self._accounting_policy is None or (
            quote.policy.content_hash != self._accounting_policy.content_hash
            or quote.prepared.provider_id != self._provider_identity
        ):
            raise ValueError("LLM_BUDGET_REQUEST_MISMATCH")
        async with database.async_session_maker() as session:
            now = await database_utc_now(session)
        if (
            quote_request(
                quote.prepared,
                self._accounting_policy,
                token_limit=quote.reserved_tokens,
                now=now,
                dispatch_timeout_seconds=self._dispatch_timeout_seconds,
            )
            != quote
        ):
            raise ValueError("LLM_BUDGET_REQUEST_MISMATCH")

    async def _validated_run(self, run_id: str) -> ResearchRun:
        async with database.async_session_maker() as session:
            run = await session.get(ResearchRun, run_id)
        if run is None:
            raise ValueError("LLM_RESEARCH_RUN_NOT_FOUND")
        profile = await CapabilityRegistry().get(
            run.capability_profile_id,
            run.capability_profile_version,
        )
        decision = await CapabilityRegistry().evaluate(
            run.capability_profile_id,
            run.capability_profile_version,
            required=("protocol_v2",),
        )
        if (
            profile is None
            or not decision.allowed
            or profile.evidence_hash != run.capability_evidence_hash
        ):
            raise ValueError("LLM_RUN_PROFILE_NOT_CURRENT")
        return run

    async def _record_invocation(
        self,
        *,
        run_id: str,
        requested_model: str,
        resolved_model: str,
        prompt_template_version: str,
        system_input_hash: str,
        input_hash: str,
        sampling_params: dict[str, Any],
        tool_manifest: tuple[str, ...],
        origin: str,
        fallback_chain: tuple[str, ...],
        token_usage: dict[str, Any],
        cost: dict[str, Any],
        output: str | None,
        provider_request_id: str | None,
        error_code: str | None,
        provider_reported_model: str | None = None,
    ) -> ResearchModelInvocation:
        async with database.async_session_maker() as session:
            invocation = ResearchModelInvocation(
                run_id=run_id,
                provider=self._provider_identity,
                requested_model=requested_model,
                resolved_model=resolved_model,
                provider_reported_model=provider_reported_model,
                provider_request_id=provider_request_id,
                prompt_template_version=prompt_template_version,
                system_input_hash=system_input_hash,
                input_hash=input_hash,
                output_hash=content_hash({"output": output}) if output is not None else None,
                sampling_params=sampling_params,
                tool_manifest=list(tool_manifest),
                origin=origin,
                transformation_chain=["redact", "typed_gateway"],
                fallback_chain=list(fallback_chain),
                token_usage=token_usage,
                cost=cost,
                error_code=error_code,
            )
            session.add(invocation)
            await session.commit()
            await session.refresh(invocation)
            return invocation


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Refuse credential-bearing keys before ordinary recursive value redaction."""

    nodes = 0

    def validate_keys(item: Any, depth: int = 0) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > 4096 or depth > 16:
            raise ValueError
        if isinstance(item, Mapping):
            for key, child in item.items():
                if type(key) is not str or redact_sensitive_payload(key) != key:
                    raise ValueError
                validate_keys(child, depth + 1)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                validate_keys(child, depth + 1)

    try:
        snapshot = dict(value)
        validate_keys(snapshot)
        redacted = redact_sensitive_payload(snapshot)
        if not isinstance(redacted, dict):
            raise ValueError
        return redacted
    except Exception:
        raise ValueError("LLM_TYPED_INPUT_INVALID") from None


def _safe_sampling_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve a typed output limit, never arbitrary token-bearing values.

    General-purpose credential redaction intentionally matches ``token`` in
    keys. A server-owned numeric ``max_tokens`` is a resource bound, not a
    credential; validate it before restoring only this exact top-level field.
    """

    snapshot = dict(value)
    safe = _safe_mapping(snapshot)
    if "max_tokens" in snapshot:
        maximum = snapshot["max_tokens"]
        if type(maximum) is not int or maximum <= 0:
            raise ValueError("LLM_SAMPLING_PARAMS_INVALID")
        safe["max_tokens"] = maximum
    return safe


def _verified_token_count(usage: Mapping[str, Any]) -> int | None:
    """Accept adapter totals only when all supplied counter forms agree."""

    totals: list[int] = []
    for first, second in (("input", "output"), ("prompt_tokens", "completion_tokens")):
        if first not in usage and second not in usage:
            continue
        values = (usage.get(first), usage.get(second))
        if any(type(value) is not int or value < 0 for value in values):
            return None
        totals.append(sum(values))
    if "total_tokens" in usage:
        total = usage["total_tokens"]
        if type(total) is not int or total < 0:
            return None
        totals.append(total)
    if not totals or any(total != totals[0] for total in totals):
        return None
    return totals[0]


def _verified_token_components(usage: Mapping[str, Any]) -> tuple[int, int] | None:
    """Different input/output tariffs require both counters, not only a total."""

    if _verified_token_count(usage) is None:
        return None
    pairs = []
    for first, second in (("input", "output"), ("prompt_tokens", "completion_tokens")):
        if first in usage and second in usage:
            pairs.append((usage[first], usage[second]))
    if not pairs or any(pair != pairs[0] for pair in pairs):
        return None
    return pairs[0]


def _validated_provider_response(response: object) -> ProviderResponse:
    """Snapshot, bound and redact every response field before side effects.

    These limits bound gateway validation, not the provider's transport/body
    allocation. Adapters must separately enforce their own transport limits.
    """

    if not isinstance(response, ProviderResponse):
        raise ValueError("LLM_PROVIDER_RESPONSE_INVALID")
    output = _response_text(response.output, 1048576, "LLM_PROVIDER_OUTPUT_INVALID")
    usage = _response_mapping(response.token_usage, "LLM_PROVIDER_USAGE_UNVERIFIED")
    cost = _response_mapping(response.cost, "LLM_PROVIDER_RESPONSE_INVALID")
    request_id = (
        None
        if response.provider_request_id is None
        else _response_text(response.provider_request_id, 256, "LLM_PROVIDER_RESPONSE_INVALID")
    )
    chain = response.fallback_chain
    if type(chain) is not tuple or len(chain) > 16:
        raise ValueError("LLM_PROVIDER_RESPONSE_INVALID")
    fallback = tuple(_response_text(item, 256, "LLM_PROVIDER_RESPONSE_INVALID") for item in chain)
    observed_model = response.observed_model
    if observed_model is not None:
        safe_model = _response_text(observed_model, 256, "LLM_PROVIDER_RESPONSE_INVALID")
        if not safe_model.strip() or safe_model != observed_model:
            raise ValueError("LLM_PROVIDER_RESPONSE_INVALID")
    return ProviderResponse(output, request_id, usage, cost, fallback, observed_model)


def _response_text(value: object, max_bytes: int, error_code: str) -> str:
    try:
        if type(value) is not str or len(value) > max_bytes or "\x00" in value:
            raise ValueError
        if len(value.encode("utf-8")) > max_bytes:
            raise ValueError
        redacted = redact_sensitive_payload(value)
        if type(redacted) is not str or len(redacted.encode("utf-8")) > max_bytes:
            raise ValueError
        return redacted
    except Exception:
        # Even URL parsing or a malformed adapter object must not expose its
        # exception text or bypass the stable failure ledger.
        raise ValueError(error_code) from None


def _response_mapping(value: object, error_code: str) -> dict[str, Any]:
    nodes = 0
    string_bytes = 0

    def account_string(item: str) -> None:
        nonlocal string_bytes
        if len(item) > 65536 or "\x00" in item:
            raise ValueError
        string_bytes += len(item.encode("utf-8"))
        if string_bytes > 65536:
            raise ValueError

    def copy_json(item: Any, depth: int = 0) -> Any:
        nonlocal nodes
        nodes += 1
        if nodes > 4096 or depth > 16:
            raise ValueError
        if item is None or type(item) in {bool, int}:
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError
            return item
        if type(item) is str:
            account_string(item)
            return item
        if isinstance(item, Mapping):
            result = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError
                account_string(key)
                # Redacting only the value is insufficient when a provider
                # embeds a credential or signed URL in the JSON key itself.
                if redact_sensitive_payload(key) != key:
                    raise ValueError
                result[key] = copy_json(child, depth + 1)
            return result
        if type(item) in {list, tuple}:
            return [copy_json(child, depth + 1) for child in item]
        raise ValueError

    try:
        if not isinstance(value, Mapping):
            raise ValueError
        snapshot = copy_json(value)
        if len(json.dumps(snapshot, allow_nan=False).encode("utf-8")) > 65536:
            raise ValueError
        safe = _safe_mapping(snapshot)
        # The generic secret filter also matches '*_tokens'. Preserve only
        # verified numeric counters, never arbitrary token-bearing strings.
        if error_code == "LLM_PROVIDER_USAGE_UNVERIFIED":
            for key in ("input", "output", "prompt_tokens", "completion_tokens", "total_tokens"):
                counter = snapshot.get(key)
                if type(counter) is int and counter >= 0:
                    safe[key] = counter
        if len(json.dumps(safe, allow_nan=False).encode("utf-8")) > 65536:
            raise ValueError
        return safe
    except Exception:
        raise ValueError(error_code) from None
