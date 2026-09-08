"""Pinned, conservative admission bounds for trusted model dispatches.

An accounting policy is a deployment-reviewed snapshot, pinned by its
canonical SHA-256.  That pin is not evidence that a provider independently
verified a tariff or tokenizer: deployments must establish that evidence before
enabling a policy.  In the absence of a model-specific tokenizer, this module
uses only the supplier-contract input ceiling; it never estimates tokens from
characters or bytes.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.research.canonical import content_hash as canonical_content_hash
from app.services.research.provider_contract import PreparedProviderRequest
from app.services.research.redaction import redact_sensitive_payload

_MAX_INT32 = 2**31 - 1
_MAX_OUTPUT_TOKENS = 131_072
_MICRO_UNITS_PER_MILLION = 1_000_000
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SCHEMA_VERSION = "model-accounting-v1"
_ACCOUNTING_CONTRACT = "ALL_INCLUSIVE_TEXT_CHAT_V1"
_OUTPUT_CONTRACT = "MAX_TOKENS_ALL_BILLABLE"
_PRICING_CONTRACT = "ADMISSION_PRICE_ALL_INCLUSIVE_V1"
_POLICY_KEYS = (
    "schema_version",
    "version",
    "provider_id",
    "model_id",
    "endpoint_hash",
    "max_billable_input_tokens",
    "max_output_tokens",
    "input_microusd_per_million",
    "output_microusd_per_million",
    "fixed_microusd",
    "valid_from",
    "expires_at",
    "evidence_hash",
    "accounting_contract",
    "output_contract",
    "pricing_contract",
)


@dataclass(frozen=True, slots=True, init=False)
class ModelAccountingPolicy:
    """A strict deployment policy for one exact provider/model/route tuple.

    Construct it through :meth:`from_mapping`.  The ``expected_hash`` is an
    operator/deployment audit pin, not a substitute for supplier accounting
    evidence.
    """

    schema_version: str
    version: str
    provider_id: str
    model_id: str
    endpoint_hash: str
    max_billable_input_tokens: int
    max_output_tokens: int
    input_microusd_per_million: int
    output_microusd_per_million: int
    fixed_microusd: int
    valid_from: str
    expires_at: str
    evidence_hash: str
    accounting_contract: str
    output_contract: str
    pricing_contract: str

    def __init__(self, **_: object) -> None:
        raise TypeError("Use ModelAccountingPolicy.from_mapping")

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_hash: str,
    ) -> ModelAccountingPolicy:
        """Validate a reviewed raw JSON policy and require its audit pin."""

        snapshot = _validated_policy_snapshot(payload)
        if not _is_hash(expected_hash) or expected_hash != canonical_content_hash(snapshot):
            raise ValueError("MODEL_ACCOUNTING_POLICY_HASH_MISMATCH")
        policy = object.__new__(cls)
        for key in _POLICY_KEYS:
            object.__setattr__(policy, key, snapshot[key])
        return policy

    def snapshot(self) -> dict[str, Any]:
        """Return a detached primitive-only representation of this policy."""

        return {key: getattr(self, key) for key in _POLICY_KEYS}

    @property
    def content_hash(self) -> str:
        """Return the canonical deployment-audit identity of this policy."""

        return canonical_content_hash(self.snapshot())

    @property
    def valid_from_at(self) -> datetime:
        """Return the validated UTC start timestamp."""

        return _parse_utc_timestamp(self.valid_from)

    @property
    def expires_at_at(self) -> datetime:
        """Return the validated UTC expiry timestamp."""

        return _parse_utc_timestamp(self.expires_at)


@dataclass(frozen=True, slots=True)
class BudgetQuote:
    """One immutable conservative token and micro-USD admission bound."""

    prepared: PreparedProviderRequest
    policy: ModelAccountingPolicy
    input_token_ceiling: int
    output_token_ceiling: int
    reserved_tokens: int
    reserved_microusd: int

    def __post_init__(self) -> None:
        try:
            if not isinstance(self.prepared, PreparedProviderRequest) or not isinstance(
                self.policy, ModelAccountingPolicy
            ):
                raise ValueError
            if not _route_matches(self.prepared, self.policy):
                raise ValueError
            if (
                type(self.input_token_ceiling) is not int
                or self.input_token_ceiling != self.policy.max_billable_input_tokens
                or type(self.output_token_ceiling) is not int
                or self.output_token_ceiling != self.prepared.max_output_tokens
                or not 0 < self.output_token_ceiling <= self.policy.max_output_tokens
            ):
                raise ValueError
            if (
                type(self.reserved_tokens) is not int
                or self.reserved_tokens != self.input_token_ceiling + self.output_token_ceiling
                or not 0 < self.reserved_tokens <= _MAX_INT32
            ):
                raise ValueError
            expected_cost = _microusd_cost(
                self.policy,
                input_tokens=self.input_token_ceiling,
                output_tokens=self.output_token_ceiling,
            )
            if (
                type(self.reserved_microusd) is not int
                or self.reserved_microusd != expected_cost
                or not 0 <= self.reserved_microusd <= _MAX_INT32
            ):
                raise ValueError
        except Exception:
            raise ValueError("MODEL_BUDGET_QUOTE_INVALID") from None

    def context(
        self,
        *,
        run_request_hash: str,
        task_id: str,
        stage_attempt_id: str,
        quota_policy_version: str,
    ) -> dict[str, Any]:
        """Return a detached durable binding without the outbound body or prompt."""

        try:
            if not _is_hash(run_request_hash):
                raise ValueError
            _identity(task_id, 128)
            _identity(stage_attempt_id, 128)
            _identity(quota_policy_version, 128)
        except Exception:
            raise ValueError("MODEL_BUDGET_CONTEXT_INVALID") from None
        return {
            "schema_version": "model-budget-quote-v1",
            "run_request_hash": run_request_hash,
            "task_id": task_id,
            "stage_attempt_id": stage_attempt_id,
            "quota_policy_version": quota_policy_version,
            "provider_id": self.prepared.provider_id,
            "model_id": self.prepared.model_id,
            "endpoint_hash": self.prepared.endpoint_hash,
            "body_hash": self.prepared.body_hash,
            "policy": deepcopy(self.policy.snapshot()),
            "policy_content_hash": self.policy.content_hash,
            "input_token_ceiling": self.input_token_ceiling,
            "output_token_ceiling": self.output_token_ceiling,
            "reserved_tokens": self.reserved_tokens,
            "reserved_microusd": self.reserved_microusd,
        }

    def settlement(self, *, input_tokens: int, output_tokens: int) -> tuple[int, int]:
        """Return bounded usage/cost only when both provider counters are known."""

        if (
            type(input_tokens) is not int
            or type(output_tokens) is not int
            or not 0 <= input_tokens <= self.input_token_ceiling
            or not 0 <= output_tokens <= self.output_token_ceiling
        ):
            raise ValueError("MODEL_BUDGET_SETTLEMENT_INVALID")
        total_tokens = input_tokens + output_tokens
        settled_microusd = _microusd_cost(
            self.policy,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if total_tokens > self.reserved_tokens or settled_microusd > self.reserved_microusd:
            raise ValueError("MODEL_BUDGET_SETTLEMENT_INVALID")
        return total_tokens, settled_microusd


def quote_request(
    prepared: PreparedProviderRequest,
    policy: ModelAccountingPolicy,
    *,
    token_limit: int,
    now: datetime,
    dispatch_timeout_seconds: float,
) -> BudgetQuote:
    """Create one no-estimate admission quote before a quota reservation."""

    try:
        if not isinstance(prepared, PreparedProviderRequest) or not isinstance(
            policy, ModelAccountingPolicy
        ):
            raise ValueError("MODEL_BUDGET_QUOTE_INVALID")
        if not _route_matches(prepared, policy):
            raise ValueError("MODEL_BUDGET_QUOTE_INVALID")
        if type(token_limit) is not int or not 0 < token_limit <= _MAX_INT32:
            raise ValueError("MODEL_BUDGET_QUOTE_INVALID")
        quoted_now = _as_utc_now(now)
        timeout = _timeout_delta(dispatch_timeout_seconds)
        if policy.valid_from_at > quoted_now or policy.expires_at_at <= quoted_now + timeout:
            raise ValueError("MODEL_BUDGET_POLICY_WINDOW_INVALID")
        if prepared.max_output_tokens > policy.max_output_tokens:
            raise ValueError("MODEL_BUDGET_QUOTE_INVALID")

        input_ceiling = policy.max_billable_input_tokens
        output_ceiling = prepared.max_output_tokens
        reserved_tokens = input_ceiling + output_ceiling
        if reserved_tokens > _MAX_INT32 or reserved_tokens > token_limit:
            raise ValueError("MODEL_BUDGET_TOKEN_LIMIT_EXCEEDED")
        reserved_microusd = _microusd_cost(
            policy,
            input_tokens=input_ceiling,
            output_tokens=output_ceiling,
        )
        if reserved_microusd > _MAX_INT32:
            raise ValueError("MODEL_BUDGET_AMOUNT_OVERFLOW")
        return BudgetQuote(
            prepared=prepared,
            policy=policy,
            input_token_ceiling=input_ceiling,
            output_token_ceiling=output_ceiling,
            reserved_tokens=reserved_tokens,
            reserved_microusd=reserved_microusd,
        )
    except ValueError as exc:
        if str(exc).startswith("MODEL_BUDGET_"):
            raise
        raise ValueError("MODEL_BUDGET_QUOTE_INVALID") from None
    except Exception:
        raise ValueError("MODEL_BUDGET_QUOTE_INVALID") from None


def _validated_policy_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    try:
        if not isinstance(payload, Mapping):
            raise ValueError
        snapshot = dict(payload)
        if set(snapshot) != set(_POLICY_KEYS) or any(type(key) is not str for key in snapshot):
            raise ValueError
        if snapshot["schema_version"] != _SCHEMA_VERSION:
            raise ValueError
        _identity(snapshot["version"], 128)
        _identity(snapshot["provider_id"], 128)
        _identity(snapshot["model_id"], 256)
        if not _is_hash(snapshot["endpoint_hash"]) or not _is_hash(snapshot["evidence_hash"]):
            raise ValueError
        _positive_int(snapshot["max_billable_input_tokens"], _MAX_INT32)
        _positive_int(snapshot["max_output_tokens"], _MAX_OUTPUT_TOKENS)
        _positive_int(snapshot["input_microusd_per_million"], _MAX_INT32)
        _positive_int(snapshot["output_microusd_per_million"], _MAX_INT32)
        if type(snapshot["fixed_microusd"]) is not int or snapshot["fixed_microusd"] < 0:
            raise ValueError
        valid_from = _parse_utc_timestamp(snapshot["valid_from"])
        expires_at = _parse_utc_timestamp(snapshot["expires_at"])
        if valid_from >= expires_at:
            raise ValueError
        if snapshot["accounting_contract"] != _ACCOUNTING_CONTRACT:
            raise ValueError
        if snapshot["output_contract"] != _OUTPUT_CONTRACT:
            raise ValueError
        if snapshot["pricing_contract"] != _PRICING_CONTRACT:
            raise ValueError
        return {key: snapshot[key] for key in _POLICY_KEYS}
    except Exception:
        raise ValueError("MODEL_ACCOUNTING_POLICY_INVALID") from None


def _route_matches(prepared: PreparedProviderRequest, policy: ModelAccountingPolicy) -> bool:
    return (
        prepared.provider_id == policy.provider_id
        and prepared.model_id == policy.model_id
        and prepared.endpoint_hash == policy.endpoint_hash
    )


def _microusd_cost(
    policy: ModelAccountingPolicy,
    *,
    input_tokens: int,
    output_tokens: int,
) -> int:
    # Preserve a conservative bound if the supplier rounds the separately
    # billable input and output categories independently.
    input_microusd = (
        input_tokens * policy.input_microusd_per_million + _MICRO_UNITS_PER_MILLION - 1
    ) // _MICRO_UNITS_PER_MILLION
    output_microusd = (
        output_tokens * policy.output_microusd_per_million + _MICRO_UNITS_PER_MILLION - 1
    ) // _MICRO_UNITS_PER_MILLION
    return policy.fixed_microusd + input_microusd + output_microusd


def _positive_int(value: object, maximum: int) -> None:
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError


def _identity(value: object, maximum: int) -> None:
    if (
        type(value) is not str
        or not value.strip()
        or len(value.encode("utf-8")) > maximum
        or "\x00" in value
        or redact_sensitive_payload(value) != value
    ):
        raise ValueError


def _is_hash(value: object) -> bool:
    return type(value) is str and _SHA256_HEX.fullmatch(value) is not None


def _parse_utc_timestamp(value: object) -> datetime:
    if type(value) is not str or not value or "T" not in value:
        raise ValueError
    try:
        rendered = f"{value[:-1]}+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(rendered)
    except ValueError:
        raise ValueError from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError
    return parsed.astimezone(timezone.utc)


def _as_utc_now(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError
    return value.astimezone(timezone.utc)


def _timeout_delta(value: object) -> timedelta:
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= 86_400:
        raise ValueError
    return timedelta(seconds=value)
