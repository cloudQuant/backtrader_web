"""Durable local-first market-data artifacts for AI research backtests.

The strategy UI is permitted to describe only an asset class, symbol, period,
and date window.  This service resolves the exact v2 contract server-side,
reads a strict local-only point-in-time view, writes a deterministic CSV below
one controlled root, and records the evidence needed to replay that input.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import hmac
import io
import json
import math
import os
import re
import stat
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_platform import (
    MdResearchDataBinding,
    MdResearchDataBindingConsumer,
    MdResearchDataBindingRevocation,
    MdResearchDataBindingScope,
)
from app.models.user import User
from app.schemas.ai_strategy_research import AIStrategyResearchRunRequest
from app.schemas.market_data_platform import MarketDataQueryRequest
from app.services.market_data.access import (
    MarketDataAccessAuthorizer,
    MarketDataAuthorizationError,
    MarketDataPrincipal,
    MarketDataQueryAccess,
)
from app.services.market_data.capability_ledger import MarketDataCapabilityEvaluation
from app.services.market_data.coverage import CoverageStatus
from app.services.market_data.dataset_contracts import (
    DEFAULT_DATASET_CONTRACT_REGISTRY,
    DatasetContractRegistryError,
)
from app.services.market_data.identity import MarketDataIdentityResolutionError
from app.services.market_data.query_resolution import MarketDataQueryResolutionError
from app.services.market_data.query_service import (
    MarketDataQueryExecution,
    MarketDataQueryServiceError,
)
from app.services.market_data.source_policy import MarketDataSourcePolicyError
from app.services.market_data.store import MarketDataStoreError

UTC = timezone.utc
_BINDING_SCHEMA_VERSION = "market-data-research-binding-v1"
_SIGNATURE_SCHEMA_VERSION = "market-data-research-binding-signature-v1"
_RUNTIME_CAPABILITY_CONTEXT_SCHEMA_VERSION = "market-data-research-runtime-capability-v1"
_RUNTIME_CAPABILITY_CONTEXT_TTL = timedelta(minutes=15)
_CSV_COLUMNS = ("datetime", "open", "high", "low", "close", "volume", "openinterest")
_ASSET_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_INTENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CAPABILITY_CONTEXT_SEAL = object()
_STRICT_RESEARCH_BARS_FAMILY_BY_ASSET_TYPE = MappingProxyType(
    {
        "stock": "stock.realtime",
        "futures": "futures.realtime",
        "bond": "bond.realtime",
        "fund": "fund.realtime",
        "option": "option.realtime",
        "fx": "fx.realtime",
        # Crypto real-time data is a quote snapshot.  Research backtests need
        # durable OHLC bars, so reserve the distinct range family instead.
        "crypto": "crypto.range",
    }
)


class MarketDataResearchBindingError(ValueError):
    """Stable fail-closed error raised by the research binding boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _QueryService(Protocol):
    async def execute(
        self,
        request: MarketDataQueryRequest,
        *,
        access: MarketDataQueryAccess | None = None,
    ) -> MarketDataQueryExecution: ...


class _QueryContracts(Protocol):
    async def resolve(
        self,
        *,
        asset_type: str,
        symbol: str,
        period: str,
        family_id: str | None = None,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class MarketDataResearchRuntimeBinding:
    """Verified server-owned artifact details for a workspace/runtime adapter."""

    binding_id: str
    binding_hash: str
    user_id: str
    intent_id: str
    signature: str
    artifact_directory: Path
    artifact_path: Path
    artifact_relative_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    manifest_hash: str
    query_semantics: Mapping[str, object]
    signature_payload: Mapping[str, object]
    runtime_capability_context: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class _MarketDataResearchCapabilityContext:
    """One authorized durable capability read for an in-process binding operation."""

    user_id: str
    capabilities: MarketDataCapabilityEvaluation
    access: MarketDataQueryAccess
    seal: object


@dataclass(frozen=True, slots=True)
class _RuntimeAccessReplay:
    """Fresh strict-replay evidence needed by the final current-read fence."""

    principal: MarketDataPrincipal
    asset_type: str
    market: str
    purpose: str
    source_snapshot_ids: tuple[str, ...]


class MarketDataResearchBindingService:
    """Bind a research request to a strict local-only durable data artifact."""

    def __init__(
        self,
        db: AsyncSession,
        query_service: _QueryService,
        query_contracts: _QueryContracts,
        access_authorizer: MarketDataAccessAuthorizer,
        artifact_root: str | Path,
        *,
        binding_signing_key: str | bytes | None = None,
        clock: Callable[[], datetime] | None = None,
        capability_context: _MarketDataResearchCapabilityContext | None = None,
    ) -> None:
        if not isinstance(db, AsyncSession):
            raise TypeError("db must be an AsyncSession")
        if not isinstance(access_authorizer, MarketDataAccessAuthorizer):
            raise TypeError("access_authorizer must be a MarketDataAccessAuthorizer")
        if not hasattr(query_service, "execute"):
            raise TypeError("query_service must implement execute")
        if not hasattr(query_contracts, "resolve"):
            raise TypeError("query_contracts must implement resolve")
        self._db = db
        self._query_service = query_service
        self._query_contracts = query_contracts
        self._access_authorizer = access_authorizer
        self._artifact_root = _controlled_artifact_root(artifact_root)
        self._binding_signing_key = _optional_signing_key(binding_signing_key)
        self._clock = clock or _utc_now
        self._capability_context = capability_context

    async def bind_request(
        self,
        *,
        user_id: str,
        request: AIStrategyResearchRunRequest,
        intent_id: str,
    ) -> AIStrategyResearchRunRequest:
        """Return a copied request carrying only an issued immutable binding token."""
        signing_key = self._require_signing_key()
        owner_id = _required_text(user_id, field_name="user_id", maximum=36)
        normalized_intent_id = _normalized_intent_id(intent_id)
        asset_type = _research_asset_type_from_request(request)
        symbol = _required_text(request.symbol, field_name="symbol", maximum=50)
        timeframe = _normalized_timeframe(request.timeframe)
        if request.timeframe_n != 1:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_TIMEFRAME_MULTIPLIER_UNSUPPORTED"
            )
        start_at, end_at = _research_window(request.start_date, request.end_date)
        cutoff = min(_trusted_now(self._clock), end_at)

        user = await self._load_owner(owner_id)
        try:
            principal = await self._access_authorizer.principal_for_user(user)
            self._access_authorizer.require_read_data(principal=principal)
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ACCESS_DENIED") from exc
        self._require_capability_context(owner_id)
        access = MarketDataQueryAccess(principal=principal, authorizer=self._access_authorizer)
        strict_bars_family_id = _require_strict_research_bars_family(
            asset_type=asset_type,
            timeframe=timeframe,
        )

        contract = await self._resolve_contract(
            asset_type=asset_type,
            symbol=symbol,
            timeframe=timeframe,
            family_id=strict_bars_family_id,
        )
        query = _strict_local_only_query(
            contract=contract,
            expected_family_id=strict_bars_family_id,
            start_at=start_at,
            end_at=end_at,
            knowledge_cutoff=cutoff,
        )
        try:
            execution = await self._query_service.execute(query, access=access)
        except (
            MarketDataAuthorizationError,
            MarketDataIdentityResolutionError,
            MarketDataQueryResolutionError,
            MarketDataQueryServiceError,
            MarketDataSourcePolicyError,
            MarketDataStoreError,
        ) as exc:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_LOCAL_QUERY_FAILED") from exc

        _validate_execution(
            execution,
            query=query,
            expected_symbol=symbol,
            expected_asset_type=asset_type,
            expected_cutoff=cutoff,
        )
        csv_content, observation_evidence = _materialize_csv(execution)
        artifact_sha256 = _sha256_bytes(csv_content)
        artifact_size = len(csv_content)
        query_semantics = _query_semantics(
            execution=execution,
            symbol=symbol,
            timeframe=timeframe,
            timeframe_n=request.timeframe_n,
        )
        material = {
            "schema_version": _BINDING_SCHEMA_VERSION,
            "owner_user_id": owner_id,
            "intent_id": normalized_intent_id,
            "query_semantics": query_semantics,
            "pit": _pit_evidence(execution),
            "artifact": {
                "sha256": artifact_sha256,
                "size_bytes": artifact_size,
                "columns": list(_CSV_COLUMNS),
            },
            "observations": observation_evidence,
        }
        binding_hash = _canonical_sha256(material)
        relative_path, artifact_path = self._artifact_destination(binding_hash)
        manifest = {
            "schema_version": _BINDING_SCHEMA_VERSION,
            "binding_hash": binding_hash,
            "material": material,
            "artifact_relative_path": relative_path,
        }
        manifest_hash = _canonical_sha256(manifest)

        existing = await self._existing_binding(binding_hash)
        if existing is not None:
            if existing.user_id != owner_id:
                raise MarketDataResearchBindingError("MARKET_DATA_BINDING_HASH_CONFLICT")
            runtime = await self._runtime_from_model(
                existing,
                user_id=owner_id,
                signature=None,
                signing_key=signing_key,
            )
            return _bound_request(request, runtime)

        self._publish_artifact(
            artifact_path=artifact_path,
            expected_relative_path=relative_path,
            binding_hash=binding_hash,
            expected_sha256=artifact_sha256,
            content=csv_content,
        )
        binding = MdResearchDataBinding(
            user_id=owner_id,
            intent_id=normalized_intent_id,
            binding_hash=binding_hash,
            binding_schema_version=_BINDING_SCHEMA_VERSION,
            status="ACTIVE",
            artifact_relative_path=relative_path,
            artifact_sha256=artifact_sha256,
            artifact_size_bytes=artifact_size,
            manifest_json=manifest,
            manifest_sha256=manifest_hash,
            canonical_id=execution.context.query.canonical_id,
            instrument_metadata_version=execution.context.query.instrument_metadata_version,
            dataset_code=execution.context.query.dataset_code,
            family_id=execution.context.query.family_id or "",
            family_contract_version=str(execution.context.query.family_contract_version or ""),
            data_kind=execution.context.query.data_kind,
            frequency=execution.context.query.frequency or "",
            source_policy_id=execution.context.query.source_policy_id or "",
            query_fingerprint=execution.context.query.query_fingerprint,
            knowledge_cutoff=execution.knowledge_cutoff,
            identity_knowledge_cutoff=execution.identity_knowledge_cutoff,
            visibility_at=execution.visibility_anchor.visible_at,
            visibility_sequence=execution.visibility_anchor.max_visibility_sequence,
            identity_visibility_at=execution.identity_visibility_anchor.visible_at,
            identity_visibility_sequence=execution.identity_visibility_anchor.max_visibility_sequence,
        )
        self._db.add(binding)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_WRITE_CONFLICT") from exc
        except SQLAlchemyError as exc:
            await self._db.rollback()
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_WRITE_FAILED") from exc

        runtime = await self._runtime_from_model(
            binding,
            user_id=owner_id,
            signature=None,
            signing_key=signing_key,
        )
        return _bound_request(request, runtime)

    async def resolve_runtime_binding(
        self,
        *,
        user_id: str,
        binding_id: str,
        binding_hash: str,
        signature: str,
        workspace_id: str,
        unit_id: str,
        intent_id: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        timeframe_n: int | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> MarketDataResearchRuntimeBinding:
        """Authorize one exact server-attested unit to read a sealed artifact.

        A valid owner HMAC is necessary but deliberately insufficient.  The
        binding must be attached by trusted AI-research orchestration to this
        precise workspace/unit/intent, and the current principal/source-policy
        decision must still authorize the sealed local evidence.
        """
        signing_key = self._require_signing_key()
        owner_id = _required_text(user_id, field_name="user_id", maximum=36)
        normalized_binding_id = _required_text(binding_id, field_name="binding_id", maximum=36)
        normalized_binding_hash = _required_sha256(binding_hash, field_name="binding_hash")
        normalized_workspace_id = _required_text(
            workspace_id,
            field_name="workspace_id",
            maximum=36,
        )
        normalized_unit_id = _required_text(unit_id, field_name="unit_id", maximum=36)
        normalized_intent_id = _normalized_intent_id(intent_id)
        binding = await self._load_runtime_binding(
            binding_id=normalized_binding_id,
            user_id=owner_id,
            binding_hash=normalized_binding_hash,
        )
        manifest = _validated_manifest(binding)
        await self._require_active_runtime_consumer(
            binding=binding,
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            intent_id=normalized_intent_id,
        )
        await self._require_research_workspace_unit(
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            binding=binding,
            signature=signature,
            intent_id=normalized_intent_id,
        )
        await self._revalidate_current_runtime_access(
            binding=binding,
            manifest=manifest,
        )

        # MySQL/InnoDB REPEATABLE READ pins ordinary SELECTs to the first
        # transaction snapshot. The prior replay can be long enough for a
        # revocation or entitlement change to commit, so another ordinary
        # SELECT in that transaction is not an authorization fence. This
        # resolver is read-only: discard the completed snapshot, reload every
        # runtime authority, then repeat the strict current-policy replay.
        await self._end_runtime_read_snapshot()
        binding = await self._load_runtime_binding(
            binding_id=normalized_binding_id,
            user_id=owner_id,
            binding_hash=normalized_binding_hash,
        )
        manifest = _validated_manifest(binding)
        await self._require_active_runtime_consumer(
            binding=binding,
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            intent_id=normalized_intent_id,
        )
        await self._require_research_workspace_unit(
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            binding=binding,
            signature=signature,
            intent_id=normalized_intent_id,
        )
        replay_access = await self._revalidate_current_runtime_access(
            binding=binding,
            manifest=manifest,
        )

        # A revocation may itself commit while the fresh replay is in flight.
        # Restart again and use locking current reads for the short final
        # authorization fence. Do not use any ORM instance from either
        # discarded snapshot to construct the runtime artifact.
        await self._end_runtime_read_snapshot()
        binding = await self._load_runtime_binding(
            binding_id=normalized_binding_id,
            user_id=owner_id,
            binding_hash=normalized_binding_hash,
            lock_current=True,
        )
        await self._require_active_runtime_consumer(
            binding=binding,
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            intent_id=normalized_intent_id,
            lock_current=True,
        )
        await self._require_research_workspace_unit(
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            binding=binding,
            signature=signature,
            intent_id=normalized_intent_id,
            lock_current=True,
        )
        try:
            final_principal = await self._access_authorizer.revalidate_principal_for_write(
                principal=replay_access.principal,
            )
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_READ_ACCESS_DENIED"
            ) from exc
        try:
            await self._access_authorizer.reauthorize_sealed_source_registries(
                principal=final_principal,
                source_snapshot_ids=replay_access.source_snapshot_ids,
                asset_type=replay_access.asset_type,
                market=replay_access.market,
                purpose=replay_access.purpose,
            )
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_SOURCE_POLICY_ACCESS_DENIED"
            ) from exc
        capability_context = self._require_capability_context(owner_id)
        runtime = await self._runtime_from_model(
            binding,
            user_id=owner_id,
            signature=signature,
            signing_key=signing_key,
        )
        supplied = (symbol, timeframe, timeframe_n, start, end)
        if any(value is not None for value in supplied):
            if any(value is None for value in supplied):
                raise MarketDataResearchBindingError(
                    "MARKET_DATA_BINDING_RUNTIME_SEMANTICS_REQUIRED"
                )
            validate_market_data_binding_runtime_semantics(
                query_semantics=runtime.query_semantics,
                symbol=str(symbol),
                timeframe=str(timeframe),
                timeframe_n=int(timeframe_n),
                start=start,
                end=end,
            )
        return self._with_runtime_capability_context(
            runtime,
            capability_context=capability_context,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            signing_key=signing_key,
        )

    async def attach_runtime_binding_consumer(
        self,
        *,
        user_id: str,
        binding_id: str,
        binding_hash: str,
        signature: str,
        intent_id: str,
        workspace_id: str,
        unit_id: str,
    ) -> None:
        """Persist a server-only authorization from a binding to one research unit.

        This method is intentionally called after trusted AI orchestration has
        created the unit and before it submits the backtest.  The generic
        workspace API has no path to invoke it.  A binding may serve several
        iteration units in one research workspace, but can never be scoped to
        a second workspace or a unit outside its issued intent.
        """
        signing_key = self._require_signing_key()
        owner_id = _required_text(user_id, field_name="user_id", maximum=36)
        normalized_binding_id = _required_text(binding_id, field_name="binding_id", maximum=36)
        normalized_binding_hash = _required_sha256(binding_hash, field_name="binding_hash")
        normalized_intent_id = _normalized_intent_id(intent_id)
        normalized_workspace_id = _required_text(
            workspace_id,
            field_name="workspace_id",
            maximum=36,
        )
        normalized_unit_id = _required_text(unit_id, field_name="unit_id", maximum=36)

        owner = await self._load_owner(owner_id)
        try:
            principal = await self._access_authorizer.principal_for_user(owner)
            self._access_authorizer.require_read_data(principal=principal)
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ACCESS_DENIED") from exc
        self._require_capability_context(owner_id)

        binding = await self._db.scalar(
            select(MdResearchDataBinding)
            .where(MdResearchDataBinding.id == normalized_binding_id)
            .with_for_update()
        )
        if binding is None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NOT_FOUND")
        if binding.user_id != owner_id:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OWNER_DENIED")
        if binding.binding_hash != normalized_binding_hash:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_HASH_MISMATCH")
        if binding.intent_id != normalized_intent_id:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")

        revoked = await self._db.scalar(
            select(MdResearchDataBindingRevocation).where(
                MdResearchDataBindingRevocation.binding_id == binding.id
            )
        )
        if revoked is not None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_REVOKED")

        # Validate the HMAC and immutable artifact before authorizing any
        # consumer.  This also rejects a revoked/invalid binding state.
        await self._runtime_from_model(
            binding,
            user_id=owner_id,
            signature=signature,
            signing_key=signing_key,
        )
        manifest = _validated_manifest(binding)
        await self._revalidate_current_runtime_access(binding=binding, manifest=manifest)
        await self._require_research_workspace_unit(
            user_id=owner_id,
            workspace_id=normalized_workspace_id,
            unit_id=normalized_unit_id,
            binding=binding,
            signature=signature,
            intent_id=normalized_intent_id,
        )

        scope = await self._db.get(MdResearchDataBindingScope, binding.id)
        if scope is None:
            scope = MdResearchDataBindingScope(
                binding_id=binding.id,
                user_id=owner_id,
                intent_id=normalized_intent_id,
                workspace_id=normalized_workspace_id,
            )
            self._db.add(scope)
        elif (
            scope.user_id != owner_id
            or scope.intent_id != normalized_intent_id
            or scope.workspace_id != normalized_workspace_id
        ):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")

        consumer = await self._db.scalar(
            select(MdResearchDataBindingConsumer).where(
                MdResearchDataBindingConsumer.unit_id == normalized_unit_id
            )
        )
        if consumer is None:
            self._db.add(
                MdResearchDataBindingConsumer(
                    binding_id=binding.id,
                    user_id=owner_id,
                    intent_id=normalized_intent_id,
                    workspace_id=normalized_workspace_id,
                    unit_id=normalized_unit_id,
                )
            )
        elif (
            consumer.binding_id != binding.id
            or consumer.user_id != owner_id
            or consumer.intent_id != normalized_intent_id
            or consumer.workspace_id != normalized_workspace_id
        ):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_CONSUMER_WRITE_CONFLICT"
            ) from exc
        except SQLAlchemyError as exc:
            await self._db.rollback()
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_CONSUMER_WRITE_FAILED"
            ) from exc

    async def revoke_runtime_binding(
        self,
        *,
        binding_id: str,
        reason_code: str,
        actor_user_id: str | None = None,
        status: str = "REVOKED",
    ) -> None:
        """Append one irreversible emergency revocation receipt for a binding.

        This service-level control is intentionally not exposed through a
        browser route.  Operations can use it after their own authorization
        procedure; runtime resolution rejects the receipt immediately.
        """
        normalized_binding_id = _required_text(binding_id, field_name="binding_id", maximum=36)
        normalized_reason = _required_text(reason_code, field_name="reason_code", maximum=128)
        normalized_status = _required_text(status, field_name="status", maximum=16).upper()
        if normalized_status not in {"REVOKED", "INVALID"}:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_REVOCATION_STATUS_INVALID")
        normalized_actor = (
            _required_text(actor_user_id, field_name="actor_user_id", maximum=36)
            if actor_user_id is not None
            else None
        )
        binding = await self._db.get(MdResearchDataBinding, normalized_binding_id)
        if binding is None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NOT_FOUND")
        existing = await self._db.scalar(
            select(MdResearchDataBindingRevocation).where(
                MdResearchDataBindingRevocation.binding_id == normalized_binding_id
            )
        )
        if existing is not None:
            if (
                existing.status == normalized_status
                and existing.reason_code == normalized_reason
                and existing.actor_user_id == normalized_actor
            ):
                return
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ALREADY_REVOKED")
        self._db.add(
            MdResearchDataBindingRevocation(
                binding_id=normalized_binding_id,
                actor_user_id=normalized_actor,
                status=normalized_status,
                reason_code=normalized_reason,
                revoked_at=_trusted_now(self._clock),
            )
        )
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ALREADY_REVOKED") from exc
        except SQLAlchemyError as exc:
            await self._db.rollback()
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_REVOCATION_WRITE_FAILED"
            ) from exc

    async def _require_active_runtime_consumer(
        self,
        *,
        binding: MdResearchDataBinding,
        user_id: str,
        workspace_id: str,
        unit_id: str,
        intent_id: str,
        lock_current: bool = False,
    ) -> None:
        if binding.intent_id != intent_id:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")
        revocation_statement = (
            select(MdResearchDataBindingRevocation)
            .where(MdResearchDataBindingRevocation.binding_id == binding.id)
            .execution_options(populate_existing=True)
        )
        if lock_current:
            revocation_statement = revocation_statement.with_for_update()
        revoked = (await self._db.execute(revocation_statement)).scalar_one_or_none()
        if revoked is not None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_REVOKED")
        scope_statement = (
            select(MdResearchDataBindingScope)
            .where(MdResearchDataBindingScope.binding_id == binding.id)
            .execution_options(populate_existing=True)
        )
        if lock_current:
            scope_statement = scope_statement.with_for_update()
        scope = (await self._db.execute(scope_statement)).scalar_one_or_none()
        if (
            scope is None
            or scope.user_id != user_id
            or scope.intent_id != intent_id
            or scope.workspace_id != workspace_id
        ):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")
        consumer_statement = (
            select(MdResearchDataBindingConsumer)
            .where(
                MdResearchDataBindingConsumer.binding_id == binding.id,
                MdResearchDataBindingConsumer.user_id == user_id,
                MdResearchDataBindingConsumer.intent_id == intent_id,
                MdResearchDataBindingConsumer.workspace_id == workspace_id,
                MdResearchDataBindingConsumer.unit_id == unit_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock_current:
            consumer_statement = consumer_statement.with_for_update()
        consumer = (await self._db.execute(consumer_statement)).scalar_one_or_none()
        if consumer is None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")

    async def _require_research_workspace_unit(
        self,
        *,
        user_id: str,
        workspace_id: str,
        unit_id: str,
        binding: MdResearchDataBinding,
        signature: str,
        intent_id: str,
        lock_current: bool = False,
    ) -> None:
        """Verify an attachment target is an owned research unit with the token."""
        from app.models.workspace import StrategyUnit, Workspace

        workspace_statement = (
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .execution_options(populate_existing=True)
        )
        unit_statement = (
            select(StrategyUnit)
            .where(StrategyUnit.id == unit_id)
            .execution_options(populate_existing=True)
        )
        if lock_current:
            workspace_statement = workspace_statement.with_for_update()
            unit_statement = unit_statement.with_for_update()
        workspace = (await self._db.execute(workspace_statement)).scalar_one_or_none()
        unit = (await self._db.execute(unit_statement)).scalar_one_or_none()
        if (
            workspace is None
            or unit is None
            or workspace.user_id != user_id
            or unit.workspace_id != workspace_id
            or str(workspace.workspace_type).strip().lower() != "research"
        ):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")
        config = dict(unit.data_config or {})
        if (
            config.get("market_data_binding_required") is not True
            or config.get("market_data_binding_id") != binding.id
            or config.get("market_data_binding_hash") != binding.binding_hash
            or config.get("market_data_binding_signature") != signature
            or config.get("market_data_binding_intent_id") != intent_id
        ):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_INTENT_DENIED")

    async def _revalidate_current_runtime_access(
        self,
        *,
        binding: MdResearchDataBinding,
        manifest: Mapping[str, object],
    ) -> _RuntimeAccessReplay:
        """Replay the sealed strict query under current entitlement and policy.

        The replay is strictly local-only and uses the original PIT window. It
        therefore cannot fetch or replace historical data, while current
        source-policy/registry checks and full evidence comparison prevent a
        revoked grant or a permitted substitute source from reusing the CSV.
        """
        semantics = _manifest_query_semantics(manifest)
        try:
            user = await self._load_owner(binding.user_id)
            principal = await self._access_authorizer.principal_for_user(user)
            self._access_authorizer.require_read_data(principal=principal)
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_READ_ACCESS_DENIED"
            ) from exc

        start_at = _parse_runtime_timestamp(semantics["full_window_start"], "full_window_start")
        end_at = _parse_runtime_timestamp(semantics["full_window_end"], "full_window_end")
        cutoff = _stored_utc(binding.knowledge_cutoff, "knowledge_cutoff")
        asset_type = str(semantics["asset_type"])
        timeframe = str(semantics["timeframe"])
        strict_bars_family_id = _require_strict_research_bars_family(
            asset_type=asset_type,
            timeframe=timeframe,
        )
        if semantics["family_id"] != strict_bars_family_id:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_CONTRACT_MISMATCH")
        contract = await self._resolve_contract(
            asset_type=asset_type,
            symbol=str(semantics["symbol"]),
            timeframe=timeframe,
            family_id=strict_bars_family_id,
        )
        query = _strict_local_only_query(
            contract=contract,
            expected_family_id=strict_bars_family_id,
            start_at=start_at,
            end_at=end_at,
            knowledge_cutoff=cutoff,
        )
        try:
            execution = await self._query_service.execute(
                query,
                access=MarketDataQueryAccess(
                    principal=principal,
                    authorizer=self._access_authorizer,
                ),
            )
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_SOURCE_POLICY_ACCESS_DENIED"
            ) from exc
        except (
            MarketDataIdentityResolutionError,
            MarketDataQueryResolutionError,
            MarketDataQueryServiceError,
            MarketDataSourcePolicyError,
            MarketDataStoreError,
        ) as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_SOURCE_POLICY_ACCESS_DENIED"
            ) from exc
        _validate_execution(
            execution,
            query=query,
            expected_symbol=str(semantics["symbol"]),
            expected_asset_type=str(semantics["asset_type"]),
            expected_cutoff=cutoff,
        )
        replay_semantics = _query_semantics(
            execution=execution,
            symbol=str(semantics["symbol"]),
            timeframe=str(semantics["timeframe"]),
            timeframe_n=int(semantics["timeframe_n"]),
        )
        if replay_semantics != semantics:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_CONTRACT_MISMATCH")
        replay_csv, replay_evidence = _materialize_csv(execution)
        material = manifest.get("material")
        if not isinstance(material, Mapping):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
        if (
            _sha256_bytes(replay_csv) != binding.artifact_sha256
            or len(replay_csv) != binding.artifact_size_bytes
            or replay_evidence != material.get("observations")
        ):
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_SOURCE_EVIDENCE_MISMATCH"
            )
        venue = execution.context.identity.venue
        if not isinstance(venue, str) or not venue.strip():
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_SOURCE_POLICY_ACCESS_DENIED"
            )
        try:
            current_principal = await self._access_authorizer.revalidate_principal(
                principal=principal
            )
        except MarketDataAuthorizationError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_READ_ACCESS_DENIED"
            ) from exc
        return _RuntimeAccessReplay(
            principal=current_principal,
            asset_type=str(execution.context.identity.asset_type),
            market=venue,
            purpose=str(execution.context.query.purpose),
            source_snapshot_ids=_sealed_source_snapshot_ids(replay_evidence),
        )

    async def _load_runtime_binding(
        self,
        *,
        binding_id: str,
        user_id: str,
        binding_hash: str,
        lock_current: bool = False,
    ) -> MdResearchDataBinding:
        """Load a binding without retaining an identity-map snapshot value."""
        statement = (
            select(MdResearchDataBinding)
            .where(MdResearchDataBinding.id == binding_id)
            .execution_options(populate_existing=True)
        )
        if lock_current:
            # InnoDB locking reads are current reads under REPEATABLE READ.
            # They appear only in the final, short authorization fence.
            statement = statement.with_for_update()
        binding = (await self._db.execute(statement)).scalar_one_or_none()
        if binding is None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NOT_FOUND")
        if binding.user_id != user_id:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OWNER_DENIED")
        if binding.binding_hash != binding_hash:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_HASH_MISMATCH")
        return binding

    async def _end_runtime_read_snapshot(self) -> None:
        """End a completed read-only replay before the next current-read fence."""
        try:
            await self._db.rollback()
        except SQLAlchemyError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_CURRENT_READ_FAILED"
            ) from exc

    async def _load_owner(self, user_id: str) -> User:
        user = (
            await self._db.execute(
                select(User).where(User.id == user_id).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if user is None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OWNER_INVALID")
        return user

    async def _resolve_contract(
        self,
        *,
        asset_type: str,
        symbol: str,
        timeframe: str,
        family_id: str,
    ) -> Mapping[str, object]:
        try:
            contract = await self._query_contracts.resolve(
                asset_type=asset_type,
                symbol=symbol,
                period=timeframe,
                family_id=family_id,
            )
        except Exception as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_CONTRACT_UNAVAILABLE"
            ) from exc
        if not isinstance(contract, Mapping):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CONTRACT_UNAVAILABLE")
        raw_request = contract.get("request")
        if not isinstance(raw_request, Mapping):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CONTRACT_INVALID")
        return dict(raw_request)

    async def _existing_binding(self, binding_hash: str) -> MdResearchDataBinding | None:
        return await self._db.scalar(
            select(MdResearchDataBinding).where(MdResearchDataBinding.binding_hash == binding_hash)
        )

    def _artifact_destination(self, binding_hash: str) -> tuple[str, Path]:
        relative_path = f"bindings/{binding_hash}/data.csv"
        artifact_path = _safe_artifact_path(
            self._artifact_root,
            relative_path=relative_path,
            binding_hash=binding_hash,
        )
        return relative_path, artifact_path

    def _publish_artifact(
        self,
        *,
        artifact_path: Path,
        expected_relative_path: str,
        binding_hash: str,
        expected_sha256: str,
        content: bytes,
    ) -> None:
        if not content:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_EMPTY")
        if _sha256_bytes(content) != expected_sha256:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_HASH_INVALID")
        _safe_artifact_path(
            self._artifact_root,
            relative_path=expected_relative_path,
            binding_hash=binding_hash,
        )
        try:
            artifact_path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            _assert_path_contained(self._artifact_root, artifact_path.parent)
            if artifact_path.exists() or artifact_path.is_symlink():
                _verify_artifact_file(
                    artifact_path,
                    expected_sha256=expected_sha256,
                    expected_size=len(content),
                    root=self._artifact_root,
                )
                return
            temporary_path = artifact_path.parent / f".{artifact_path.name}.{uuid.uuid4().hex}.tmp"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(temporary_path, flags, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    descriptor = -1
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary_path, 0o440)
                try:
                    os.link(temporary_path, artifact_path, follow_symlinks=False)
                except FileExistsError:
                    _verify_artifact_file(
                        artifact_path,
                        expected_sha256=expected_sha256,
                        expected_size=len(content),
                        root=self._artifact_root,
                    )
                else:
                    _fsync_directory(artifact_path.parent)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
                if temporary_path.exists() or temporary_path.is_symlink():
                    temporary_path.unlink()
        except MarketDataResearchBindingError:
            raise
        except OSError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_ARTIFACT_WRITE_FAILED"
            ) from exc

    async def _runtime_from_model(
        self,
        binding: MdResearchDataBinding,
        *,
        user_id: str,
        signature: str | None,
        signing_key: bytes,
    ) -> MarketDataResearchRuntimeBinding:
        if binding.status != "ACTIVE":
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_INACTIVE")
        manifest = _validated_manifest(binding)
        query_semantics = _manifest_query_semantics(manifest)
        artifact_path = _safe_artifact_path(
            self._artifact_root,
            relative_path=binding.artifact_relative_path,
            binding_hash=binding.binding_hash,
        )
        _verify_artifact_file(
            artifact_path,
            expected_sha256=binding.artifact_sha256,
            expected_size=binding.artifact_size_bytes,
            root=self._artifact_root,
        )
        payload = build_market_data_binding_signature_payload(
            binding_id=binding.id,
            binding_hash=binding.binding_hash,
            owner_user_id=user_id,
            artifact_relative_path=binding.artifact_relative_path,
            artifact_sha256=binding.artifact_sha256,
            artifact_size_bytes=binding.artifact_size_bytes,
            query_semantics=query_semantics,
        )
        expected_signature = sign_market_data_binding_payload(payload, signing_key)
        if signature is not None:
            verified_payload = verify_market_data_binding_signature(signature, signing_key)
            if dict(verified_payload) != payload:
                raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
        return MarketDataResearchRuntimeBinding(
            binding_id=binding.id,
            binding_hash=binding.binding_hash,
            user_id=user_id,
            intent_id=binding.intent_id,
            signature=expected_signature,
            artifact_directory=artifact_path.parent,
            artifact_path=artifact_path,
            artifact_relative_path=binding.artifact_relative_path,
            artifact_sha256=binding.artifact_sha256,
            artifact_size_bytes=binding.artifact_size_bytes,
            manifest_hash=binding.manifest_sha256,
            query_semantics=MappingProxyType(dict(query_semantics)),
            signature_payload=MappingProxyType(payload),
        )

    def _require_signing_key(self) -> bytes:
        if self._binding_signing_key is None:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNING_KEY_REQUIRED")
        return self._binding_signing_key

    def _require_capability_context(
        self,
        user_id: str,
    ) -> _MarketDataResearchCapabilityContext | None:
        """Require the production builder's current durable bridge decision.

        Explicitly injected query-service doubles remain supported for isolated
        unit tests.  Every production composition goes through the public
        builder below and therefore carries a sealed context rather than
        inferring approval from environment settings or an earlier request.
        """
        context = self._capability_context
        if context is None:
            return None
        if (
            context.seal is not _CAPABILITY_CONTEXT_SEAL
            or context.user_id != user_id
            or not context.capabilities.response.query_v2_enabled
            or not context.capabilities.response.research_backtest_bridge_enabled
        ):
            raise MarketDataResearchBindingError("MARKET_DATA_BRIDGE_DISABLED")
        return context

    def _with_runtime_capability_context(
        self,
        runtime: MarketDataResearchRuntimeBinding,
        *,
        capability_context: _MarketDataResearchCapabilityContext | None,
        workspace_id: str,
        unit_id: str,
        signing_key: bytes,
    ) -> MarketDataResearchRuntimeBinding:
        """Attach the short-lived permit required by the synchronous child runner."""
        if capability_context is None:
            return runtime
        issued_at = _trusted_now(self._clock)
        expires_at = issued_at + _RUNTIME_CAPABILITY_CONTEXT_TTL
        payload = build_market_data_runtime_capability_context_payload(
            binding_id=runtime.binding_id,
            binding_hash=runtime.binding_hash,
            owner_user_id=runtime.user_id,
            workspace_id=workspace_id,
            unit_id=unit_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        return replace(
            runtime,
            runtime_capability_context=MappingProxyType(
                {
                    **payload,
                    "signature": sign_market_data_runtime_capability_context(payload, signing_key),
                }
            ),
        )


def market_data_research_bridge_evaluation_required(settings: object) -> bool:
    """Return whether operator kill switches permit a durable bridge evaluation.

    This predicate is intentionally only a narrowing control.  ``True`` does
    not enable a bridge; callers must still evaluate the durable lifecycle
    ledger before imposing a binding requirement.
    """
    return bool(getattr(settings, "MARKET_DATA_QUERY_V2_ENABLED", False)) and bool(
        getattr(settings, "MARKET_DATA_RESEARCH_BACKTEST_BRIDGE_ENABLED", False)
    )


async def market_data_research_bridge_is_effective(
    db: AsyncSession,
    *,
    settings: object | None = None,
) -> bool:
    """Return the current durable decision that makes a research binding mandatory.

    This control-plane read deliberately happens before the request enters the
    research binding service.  It does not authorize ``data:read``: disabled
    deployments must preserve their legacy research path for users who only
    have the ordinary research permission.  When the ledger cannot be read,
    though, treating that unknown state as a disabled bridge would create a
    fail-open path around an already-deployed strict binding requirement.
    """
    from app.api.data.queries import evaluate_market_data_capabilities
    from app.config import get_settings

    if not isinstance(db, AsyncSession):
        raise TypeError("db must be an AsyncSession")
    effective_settings = get_settings() if settings is None else settings
    # Settings are only an operator kill switch here.  A disabled switch can
    # preserve the legacy route without consulting a temporarily unavailable
    # ledger, but an enabled switch never grants the bridge by itself: the
    # durable evaluator below must still attest both capabilities.
    if not market_data_research_bridge_evaluation_required(effective_settings):
        return False
    try:
        capabilities = await evaluate_market_data_capabilities(db, settings=effective_settings)
    except SQLAlchemyError as exc:
        try:
            await db.rollback()
        except SQLAlchemyError:
            pass
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_CAPABILITY_CONTEXT_UNAVAILABLE"
        ) from exc

    if any(
        getattr(state, "reason_code", None) == "CAPABILITY_LEDGER_UNAVAILABLE"
        for state in capabilities.response.capability_states
    ):
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_CAPABILITY_CONTEXT_UNAVAILABLE"
        )
    return bool(
        capabilities.response.query_v2_enabled
        and capabilities.response.research_backtest_bridge_enabled
    )


async def build_market_data_research_binding_service(
    db: AsyncSession,
    *,
    user_id: str,
) -> MarketDataResearchBindingService:
    """Compose a binding boundary after current user and durable capability checks.

    This is the production composition path.  It intentionally accepts a
    concrete user id instead of FastAPI dependencies, performs the data-read
    authorization first, and only then evaluates the durable capability
    ledger.  No binding artifact, workspace attachment, or task snapshot can
    be created when that evidence is missing or stale.
    """
    from app.api.data.base import build_legacy_market_data_query_contract_resolver
    from app.api.data.queries import (
        build_market_data_query_service,
        evaluate_market_data_capabilities,
    )
    from app.config import get_settings

    if not isinstance(db, AsyncSession):
        raise TypeError("db must be an AsyncSession")
    owner_id = _required_text(user_id, field_name="user_id", maximum=36)
    authorizer = MarketDataAccessAuthorizer(db)
    try:
        owner = (
            await db.execute(
                select(User).where(User.id == owner_id).execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        await db.rollback()
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_CAPABILITY_CONTEXT_UNAVAILABLE"
        ) from exc
    if owner is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OWNER_INVALID")
    try:
        principal = await authorizer.principal_for_user(owner)
        authorizer.require_read_data(principal=principal)
    except MarketDataAuthorizationError as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ACCESS_DENIED") from exc

    capabilities = await evaluate_market_data_capabilities(db)
    if not (
        capabilities.response.query_v2_enabled
        and capabilities.response.research_backtest_bridge_enabled
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BRIDGE_DISABLED")
    capability_context = _MarketDataResearchCapabilityContext(
        user_id=owner_id,
        capabilities=capabilities,
        access=MarketDataQueryAccess(principal=principal, authorizer=authorizer),
        seal=_CAPABILITY_CONTEXT_SEAL,
    )
    settings = get_settings()
    return MarketDataResearchBindingService(
        db,
        build_market_data_query_service(db, capabilities),
        build_legacy_market_data_query_contract_resolver(db, settings=settings),
        authorizer,
        settings.MARKET_DATA_RESEARCH_ARTIFACT_ROOT,
        binding_signing_key=settings.MARKET_DATA_RESEARCH_ARTIFACT_SIGNING_KEY,
        capability_context=capability_context,
    )


def build_market_data_binding_signature_payload(
    *,
    binding_id: str,
    binding_hash: str,
    owner_user_id: str,
    artifact_relative_path: str,
    artifact_sha256: str,
    artifact_size_bytes: int,
    query_semantics: Mapping[str, object],
) -> dict[str, object]:
    """Build the exact pure payload authenticated by a binding signature token."""
    return {
        "schema_version": _SIGNATURE_SCHEMA_VERSION,
        "binding_id": _required_text(binding_id, field_name="binding_id", maximum=36),
        "binding_hash": _required_sha256(binding_hash, field_name="binding_hash"),
        "owner_user_id": _required_text(owner_user_id, field_name="owner_user_id", maximum=36),
        "artifact_relative_path": _required_relative_artifact_path(artifact_relative_path),
        "artifact_sha256": _required_sha256(artifact_sha256, field_name="artifact_sha256"),
        "artifact_size_bytes": _required_positive_int(artifact_size_bytes, "artifact_size_bytes"),
        "query_semantics": _validated_query_semantics(query_semantics),
    }


def sign_market_data_binding_payload(
    payload: Mapping[str, object], signing_key: str | bytes
) -> str:
    """Return a self-contained canonical-payload-plus-HMAC binding token."""
    key = _required_signing_key(signing_key)
    canonical = _canonical_json(dict(payload)).encode("utf-8")
    encoded = base64.urlsafe_b64encode(canonical).decode("ascii").rstrip("=")
    digest = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    return f"{encoded}.{digest}"


def verify_market_data_binding_signature(
    signature: str,
    signing_key: str | bytes,
) -> Mapping[str, object]:
    """Verify a self-contained signature and reject noncanonical token bodies."""
    key = _required_signing_key(signing_key)
    if not isinstance(signature, str) or signature.count(".") != 1:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
    encoded, supplied_digest = signature.split(".", 1)
    if not encoded or _SHA256_PATTERN.fullmatch(supplied_digest) is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
    try:
        canonical = base64.urlsafe_b64decode(encoded + ("=" * (-len(encoded) % 4)))
        decoded = json.loads(canonical.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID") from exc
    if not isinstance(decoded, dict) or _canonical_json(decoded).encode("utf-8") != canonical:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
    expected_digest = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_digest, expected_digest):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
    expected_keys = {
        "schema_version",
        "binding_id",
        "binding_hash",
        "owner_user_id",
        "artifact_relative_path",
        "artifact_sha256",
        "artifact_size_bytes",
        "query_semantics",
    }
    if set(decoded) != expected_keys or decoded.get("schema_version") != _SIGNATURE_SCHEMA_VERSION:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
    try:
        payload = build_market_data_binding_signature_payload(
            binding_id=str(decoded["binding_id"]),
            binding_hash=str(decoded["binding_hash"]),
            owner_user_id=str(decoded["owner_user_id"]),
            artifact_relative_path=str(decoded["artifact_relative_path"]),
            artifact_sha256=str(decoded["artifact_sha256"]),
            artifact_size_bytes=decoded["artifact_size_bytes"],
            query_semantics=decoded["query_semantics"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID") from exc
    if payload != decoded:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNATURE_INVALID")
    return MappingProxyType(payload)


def build_market_data_runtime_capability_context_payload(
    *,
    binding_id: str,
    binding_hash: str,
    owner_user_id: str,
    workspace_id: str,
    unit_id: str,
    issued_at: datetime,
    expires_at: datetime,
) -> dict[str, object]:
    """Build the short-lived server-only permit consumed by a child runtime.

    The context is separate from the durable binding HMAC: a binding proves
    immutable data provenance, whereas this permit proves that the current
    request evaluated the durable capability ledger before its runtime config
    was materialized.  Keep it deliberately small and scope it to the exact
    binding owner and workspace unit.
    """
    normalized_issued_at = _aware_utc(issued_at, "issued_at")
    normalized_expires_at = _aware_utc(expires_at, "expires_at")
    lifetime = normalized_expires_at - normalized_issued_at
    if lifetime <= timedelta(0) or lifetime > _RUNTIME_CAPABILITY_CONTEXT_TTL:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    return {
        "schema_version": _RUNTIME_CAPABILITY_CONTEXT_SCHEMA_VERSION,
        "binding_id": _required_text(binding_id, field_name="binding_id", maximum=36),
        "binding_hash": _required_sha256(binding_hash, field_name="binding_hash"),
        "owner_user_id": _required_text(owner_user_id, field_name="owner_user_id", maximum=36),
        "workspace_id": _required_text(workspace_id, field_name="workspace_id", maximum=36),
        "unit_id": _required_text(unit_id, field_name="unit_id", maximum=36),
        "issued_at": _iso_utc(normalized_issued_at),
        "expires_at": _iso_utc(normalized_expires_at),
    }


def sign_market_data_runtime_capability_context(
    payload: Mapping[str, object],
    signing_key: str | bytes,
) -> str:
    """Sign one canonical runtime-capability payload with the server key."""
    key = _required_signing_key(signing_key)
    canonical = _canonical_json(dict(payload)).encode("utf-8")
    encoded = base64.urlsafe_b64encode(canonical).decode("ascii").rstrip("=")
    digest = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    return f"{encoded}.{digest}"


def verify_market_data_runtime_capability_context(
    context: Mapping[str, object],
    signing_key: str | bytes,
    *,
    binding_id: str,
    binding_hash: str,
    owner_user_id: str,
    workspace_id: str | None = None,
    unit_id: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Mapping[str, object]:
    """Verify a request-scoped permit before a synchronous artifact read.

    The runtime may be invoked without an HTTP request or an async database
    session.  It must therefore require this server-signed, expiring context
    rather than reopening a removed settings gate or assuming a prior service
    call was authorized.
    """
    if not isinstance(context, Mapping):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_REQUIRED")
    raw_context = dict(context)
    expected_keys = {
        "schema_version",
        "binding_id",
        "binding_hash",
        "owner_user_id",
        "workspace_id",
        "unit_id",
        "issued_at",
        "expires_at",
        "signature",
    }
    if set(raw_context) != expected_keys:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    signature = raw_context.pop("signature")
    if not isinstance(signature, str) or signature.count(".") != 1:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    encoded, supplied_digest = signature.split(".", 1)
    if not encoded or _SHA256_PATTERN.fullmatch(supplied_digest) is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    try:
        canonical = base64.urlsafe_b64decode(encoded + ("=" * (-len(encoded) % 4)))
        decoded = json.loads(canonical.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID"
        ) from exc
    if not isinstance(decoded, dict) or _canonical_json(decoded).encode("utf-8") != canonical:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    expected_digest = hmac.new(
        _required_signing_key(signing_key), canonical, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied_digest, expected_digest):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    expected_payload_keys = expected_keys - {"signature"}
    if (
        set(decoded) != expected_payload_keys
        or decoded.get("schema_version") != _RUNTIME_CAPABILITY_CONTEXT_SCHEMA_VERSION
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    try:
        payload = build_market_data_runtime_capability_context_payload(
            binding_id=decoded["binding_id"],
            binding_hash=decoded["binding_hash"],
            owner_user_id=decoded["owner_user_id"],
            workspace_id=decoded["workspace_id"],
            unit_id=decoded["unit_id"],
            issued_at=_parse_runtime_timestamp(decoded["issued_at"], "issued_at"),
            expires_at=_parse_runtime_timestamp(decoded["expires_at"], "expires_at"),
        )
    except (KeyError, TypeError, ValueError, MarketDataResearchBindingError) as exc:
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID"
        ) from exc
    if payload != decoded:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    try:
        expected_binding_id = _required_text(binding_id, field_name="binding_id", maximum=36)
        expected_binding_hash = _required_sha256(binding_hash, field_name="binding_hash")
        expected_owner_user_id = _required_text(
            owner_user_id, field_name="owner_user_id", maximum=36
        )
        expected_workspace_id = (
            _required_text(workspace_id, field_name="workspace_id", maximum=36)
            if workspace_id is not None
            else None
        )
        expected_unit_id = (
            _required_text(unit_id, field_name="unit_id", maximum=36)
            if unit_id is not None
            else None
        )
    except MarketDataResearchBindingError as exc:
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID"
        ) from exc
    if (
        payload["binding_id"] != expected_binding_id
        or payload["binding_hash"] != expected_binding_hash
        or payload["owner_user_id"] != expected_owner_user_id
        or (expected_workspace_id is not None and payload["workspace_id"] != expected_workspace_id)
        or (expected_unit_id is not None and payload["unit_id"] != expected_unit_id)
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_INVALID")
    now = _trusted_now(clock or _utc_now)
    issued_at = _parse_runtime_timestamp(payload["issued_at"], "issued_at")
    expires_at = _parse_runtime_timestamp(payload["expires_at"], "expires_at")
    if now < issued_at or now >= expires_at:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CAPABILITY_CONTEXT_EXPIRED")
    return MappingProxyType(payload)


def validate_market_data_binding_runtime_semantics(
    *,
    query_semantics: Mapping[str, object],
    symbol: str,
    timeframe: str,
    timeframe_n: int,
    start: str | datetime,
    end: str | datetime,
) -> None:
    """Allow only a same-identity, same-timeframe subset of the sealed window."""
    semantics = _validated_query_semantics(query_semantics)
    if (
        _required_text(symbol, field_name="symbol", maximum=50) != semantics["symbol"]
        or _normalized_timeframe(timeframe) != semantics["timeframe"]
        or timeframe_n != semantics["timeframe_n"]
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_SEMANTICS_MISMATCH")
    start_at = _parse_runtime_window_timestamp(start, field_name="start", inclusive_end=False)
    end_at = _parse_runtime_window_timestamp(end, field_name="end", inclusive_end=True)
    full_start = _parse_runtime_timestamp(semantics["full_window_start"], field_name="full_start")
    full_end = _parse_runtime_timestamp(semantics["full_window_end"], field_name="full_end")
    if start_at >= end_at or start_at < full_start or end_at > full_end:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_WINDOW_INVALID")


def _bound_request(
    request: AIStrategyResearchRunRequest,
    runtime: MarketDataResearchRuntimeBinding,
) -> AIStrategyResearchRunRequest:
    return request.model_copy(
        update={
            "data_config": {
                "market_data_asset_type": runtime.query_semantics["asset_type"],
                "market_data_binding_id": runtime.binding_id,
                "market_data_binding_hash": runtime.binding_hash,
                "market_data_binding_signature": runtime.signature,
                "market_data_binding_intent_id": runtime.intent_id,
                "market_data_binding_required": True,
            }
        }
    )


def _research_asset_type_from_request(request: AIStrategyResearchRunRequest) -> str:
    data_config = request.data_config
    if not isinstance(data_config, dict):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CLIENT_DATA_CONFIG_FORBIDDEN")
    if set(data_config) != {"market_data_asset_type"}:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CLIENT_DATA_CONFIG_FORBIDDEN")
    value = data_config.get("market_data_asset_type")
    if not isinstance(value, str):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ASSET_TYPE_REQUIRED")
    normalized = value.strip().lower()
    if _ASSET_TYPE_PATTERN.fullmatch(normalized) is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ASSET_TYPE_INVALID")
    return normalized


def _normalized_intent_id(value: object) -> str:
    if not isinstance(value, str) or _INTENT_ID_PATTERN.fullmatch(value.strip()) is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_INTENT_INVALID")
    return value.strip()


def _normalized_timeframe(value: object) -> str:
    if not isinstance(value, str):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_TIMEFRAME_UNSUPPORTED")
    normalized = value.strip().lower()
    if normalized not in {"1d", "1w", "1mo"}:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_TIMEFRAME_UNSUPPORTED")
    return normalized


def _strict_research_bars_family_id(asset_type: str) -> str:
    """Return the server-owned family reserved for strict research OHLC bars."""
    family_id = _STRICT_RESEARCH_BARS_FAMILY_BY_ASSET_TYPE.get(asset_type)
    if family_id is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_STRICT_BARS_FAMILY_UNSUPPORTED")
    return family_id


def _require_strict_research_bars_family(*, asset_type: str, timeframe: str) -> str:
    """Fail before contract, provider, or artifact I/O unless bars are executable."""
    family_id = _strict_research_bars_family_id(asset_type)
    try:
        contract = DEFAULT_DATASET_CONTRACT_REGISTRY.ready_contract_for(
            family_id=family_id,
            asset_type=asset_type,
        )
    except DatasetContractRegistryError as exc:
        if exc.code == "DATA_FAMILY_UNCONFIGURED":
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_STRICT_BARS_FAMILY_UNCONFIGURED"
            ) from exc
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_STRICT_BARS_FAMILY_INVALID") from exc
    if contract.data_kind != "bars":
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_STRICT_BARS_FAMILY_INVALID")
    if timeframe not in contract.frequencies:
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_STRICT_BARS_TIMEFRAME_UNSUPPORTED"
        )
    return family_id


def _normalized_asset_type(value: object) -> str:
    if not isinstance(value, str):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    normalized = value.strip().lower()
    if _ASSET_TYPE_PATTERN.fullmatch(normalized) is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return normalized


def _research_window(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    if start is None or end is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_DATE_REQUIRED")
    start_at = _parse_research_date(start, field_name="start_date", inclusive_end=False)
    end_at = _parse_research_date(end, field_name="end_date", inclusive_end=True)
    if start_at >= end_at:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_WINDOW_INVALID")
    return start_at, end_at


def _parse_research_date(value: str, *, field_name: str, inclusive_end: bool) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_DATE_INVALID")
    rendered = value.strip()
    try:
        if len(rendered) == 10:
            parsed_date = date.fromisoformat(rendered)
            result = datetime.combine(parsed_date, time.min, tzinfo=UTC)
            return result + timedelta(days=1) if inclusive_end else result
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_DATE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_DATE_TIMEZONE_REQUIRED")
    return parsed.astimezone(UTC)


def _strict_local_only_query(
    *,
    contract: Mapping[str, object],
    expected_family_id: str,
    start_at: datetime,
    end_at: datetime,
    knowledge_cutoff: datetime,
) -> MarketDataQueryRequest:
    payload = dict(contract)
    payload.update(
        {
            "start": start_at,
            "end": end_at,
            "mode": "local_only",
            "purpose": "backtest",
            "consistency": "strict",
            "knowledge_cutoff": knowledge_cutoff,
            "page_size": 2000,
        }
    )
    payload.pop("cursor", None)
    try:
        query = MarketDataQueryRequest.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CONTRACT_INVALID") from exc
    if (
        query.family_id != expected_family_id
        or query.data_kind != "bars"
        or query.mode != "local_only"
        or query.purpose != "backtest"
        or query.consistency != "strict"
        or query.knowledge_cutoff != knowledge_cutoff
        or query.cursor is not None
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CONTRACT_INVALID")
    return query


def _validate_execution(
    execution: object,
    *,
    query: MarketDataQueryRequest,
    expected_symbol: str,
    expected_asset_type: str,
    expected_cutoff: datetime,
) -> None:
    if not isinstance(execution, MarketDataQueryExecution):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_EXECUTION_INVALID")
    context_query = execution.context.query
    context_identity = execution.context.identity
    if (
        context_query.mode != "local_only"
        or context_query.purpose != "backtest"
        or context_query.consistency != "strict"
        or context_query.data_kind != "bars"
        or context_query.start != query.start
        or context_query.end != query.end
        or context_query.family_id != query.family_id
        or context_query.frequency != query.frequency
        or execution.knowledge_cutoff != expected_cutoff
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_EXECUTION_INVALID")
    if context_identity.asset_type != expected_asset_type:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_IDENTITY_MISMATCH")
    display_symbol = getattr(context_identity.identity, "display_symbol", None)
    if display_symbol != expected_symbol:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_IDENTITY_MISMATCH")
    if execution.fetches:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_FETCH_FORBIDDEN")
    if execution.next_cursor is not None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_PAGINATION_FORBIDDEN")
    status = getattr(execution.coverage.status, "value", execution.coverage.status)
    if status != CoverageStatus.COMPLETE.value:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_LOCAL_INCOMPLETE")


def _materialize_csv(execution: MarketDataQueryExecution) -> tuple[bytes, list[dict[str, object]]]:
    rows = sorted(
        execution.observations,
        key=lambda item: (
            _aware_utc(item.event_at, "event_at"),
            item.visibility_sequence,
            item.revision_number,
            item.revision_id,
        ),
    )
    if not rows:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NO_OBSERVATIONS")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    evidence: list[dict[str, object]] = []
    previous_event_at: datetime | None = None
    for item in rows:
        event_at = _aware_utc(item.event_at, "event_at")
        if previous_event_at == event_at:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_DUPLICATE_EVENT")
        previous_event_at = event_at
        fields = item.fields
        if not isinstance(fields, Mapping):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OBSERVATION_INVALID")
        open_value = _csv_required_number(fields.get("open"), "open")
        high_value = _csv_required_number(fields.get("high"), "high")
        low_value = _csv_required_number(fields.get("low"), "low")
        close_value = _csv_required_number(fields.get("close"), "close")
        volume_value = _csv_optional_number(fields.get("volume"), "volume")
        open_interest = fields.get("openinterest", fields.get("open_interest"))
        open_interest_value = _csv_optional_number(open_interest, "openinterest")
        writer.writerow(
            (
                _iso_utc(event_at),
                open_value,
                high_value,
                low_value,
                close_value,
                volume_value,
                open_interest_value,
            )
        )
        evidence.append(
            {
                "revision_id": _required_text(item.revision_id, "revision_id", 36),
                "source_snapshot_id": _required_text(
                    item.source_snapshot_id,
                    "source_snapshot_id",
                    36,
                ),
                "event_at": _iso_utc(event_at),
                "available_at": _iso_utc(_aware_utc(item.available_at, "available_at")),
                "visibility_sequence": _required_nonnegative_int(
                    item.visibility_sequence,
                    "visibility_sequence",
                ),
                "revision_number": _required_positive_int(item.revision_number, "revision_number"),
            }
        )
    return output.getvalue().encode("utf-8"), evidence


def _sealed_source_snapshot_ids(evidence: object) -> tuple[str, ...]:
    """Return every immutable source snapshot that contributed sealed bytes."""
    if not isinstance(evidence, list):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    source_snapshot_ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
        source_snapshot_ids.add(
            _required_text(item.get("source_snapshot_id"), "source_snapshot_id", 36)
        )
    if not source_snapshot_ids:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NO_OBSERVATIONS")
    return tuple(sorted(source_snapshot_ids))


def _query_semantics(
    *,
    execution: MarketDataQueryExecution,
    symbol: str,
    timeframe: str,
    timeframe_n: int,
) -> dict[str, object]:
    query = execution.context.query
    return _validated_query_semantics(
        {
            "asset_type": execution.context.identity.asset_type,
            "symbol": symbol,
            "timeframe": timeframe,
            "timeframe_n": timeframe_n,
            "full_window_start": _iso_utc(query.start),
            "full_window_end": _iso_utc(query.end),
            "canonical_id": query.canonical_id,
            "dataset_code": query.dataset_code,
            "family_id": query.family_id,
            "family_contract_version": query.family_contract_version,
            "data_kind": query.data_kind,
            "frequency": query.frequency,
            "source_policy_id": query.source_policy_id,
            "instrument_metadata_version": query.instrument_metadata_version,
            "query_fingerprint": query.query_fingerprint,
        }
    )


def _pit_evidence(execution: MarketDataQueryExecution) -> dict[str, object]:
    return {
        "knowledge_cutoff": _iso_utc(execution.knowledge_cutoff),
        "identity_knowledge_cutoff": _iso_utc(execution.identity_knowledge_cutoff),
        "visibility_at": _iso_utc(execution.visibility_anchor.visible_at),
        "visibility_sequence": execution.visibility_anchor.max_visibility_sequence,
        "identity_visibility_at": _iso_utc(execution.identity_visibility_anchor.visible_at),
        "identity_visibility_sequence": execution.identity_visibility_anchor.max_visibility_sequence,
    }


def _validated_manifest(binding: MdResearchDataBinding) -> Mapping[str, object]:
    manifest = binding.manifest_json
    if (
        not isinstance(manifest, Mapping)
        or _canonical_sha256(dict(manifest)) != binding.manifest_sha256
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    if (
        manifest.get("schema_version") != _BINDING_SCHEMA_VERSION
        or manifest.get("binding_hash") != binding.binding_hash
        or manifest.get("artifact_relative_path") != binding.artifact_relative_path
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    material = manifest.get("material")
    if not isinstance(material, Mapping):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    if _canonical_sha256(dict(material)) != binding.binding_hash:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    _validate_material_matches_binding(binding, material)
    artifact = material.get("artifact")
    if not isinstance(artifact, Mapping) or (
        artifact.get("sha256") != binding.artifact_sha256
        or artifact.get("size_bytes") != binding.artifact_size_bytes
        or artifact.get("columns") != list(_CSV_COLUMNS)
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return MappingProxyType(dict(manifest))


def _validate_material_matches_binding(
    binding: MdResearchDataBinding,
    material: Mapping[str, object],
) -> None:
    """Require the signed manifest to agree with every relational audit axis.

    The JSON manifest and its hash preserve the full immutable receipt, while
    selected columns make operational lookup possible.  Runtime resolution
    must bind those two representations together so a direct database update
    cannot silently change an identity, contract, or PIT boundary.
    """
    expected_material_keys = {
        "schema_version",
        "owner_user_id",
        "intent_id",
        "query_semantics",
        "pit",
        "artifact",
        "observations",
    }
    if set(material) != expected_material_keys:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    if (
        binding.binding_schema_version != _BINDING_SCHEMA_VERSION
        or material.get("schema_version") != _BINDING_SCHEMA_VERSION
        or material.get("owner_user_id") != binding.user_id
        or material.get("intent_id") != binding.intent_id
    ):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")

    semantics = _validated_query_semantics(material.get("query_semantics"))
    expected_semantic_columns = {
        "canonical_id": binding.canonical_id,
        "dataset_code": binding.dataset_code,
        "family_id": binding.family_id,
        "family_contract_version": binding.family_contract_version,
        "data_kind": binding.data_kind,
        "frequency": binding.frequency,
        "source_policy_id": binding.source_policy_id,
        "instrument_metadata_version": binding.instrument_metadata_version,
        "query_fingerprint": binding.query_fingerprint,
    }
    if any(semantics[key] != value for key, value in expected_semantic_columns.items()):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")

    pit = material.get("pit")
    if not isinstance(pit, Mapping) or set(pit) != {
        "knowledge_cutoff",
        "identity_knowledge_cutoff",
        "visibility_at",
        "visibility_sequence",
        "identity_visibility_at",
        "identity_visibility_sequence",
    }:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    expected_pit = {
        "knowledge_cutoff": _iso_utc(_stored_utc(binding.knowledge_cutoff, "knowledge_cutoff")),
        "identity_knowledge_cutoff": _iso_utc(
            _stored_utc(binding.identity_knowledge_cutoff, "identity_knowledge_cutoff")
        ),
        "visibility_at": _iso_utc(_stored_utc(binding.visibility_at, "visibility_at")),
        "visibility_sequence": binding.visibility_sequence,
        "identity_visibility_at": _iso_utc(
            _stored_utc(binding.identity_visibility_at, "identity_visibility_at")
        ),
        "identity_visibility_sequence": binding.identity_visibility_sequence,
    }
    if dict(pit) != expected_pit:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    if not isinstance(material.get("observations"), list):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")


def _manifest_query_semantics(manifest: Mapping[str, object]) -> dict[str, object]:
    material = manifest.get("material")
    if not isinstance(material, Mapping):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return _validated_query_semantics(material.get("query_semantics"))


def _validated_query_semantics(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    expected_keys = {
        "asset_type",
        "symbol",
        "timeframe",
        "timeframe_n",
        "full_window_start",
        "full_window_end",
        "canonical_id",
        "dataset_code",
        "family_id",
        "family_contract_version",
        "data_kind",
        "frequency",
        "source_policy_id",
        "instrument_metadata_version",
        "query_fingerprint",
    }
    if set(value) != expected_keys:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    normalized = {
        "asset_type": _normalized_asset_type(value["asset_type"]),
        "symbol": _required_text(value["symbol"], "symbol", 50),
        "timeframe": _normalized_timeframe(value["timeframe"]),
        "timeframe_n": _required_positive_int(value["timeframe_n"], "timeframe_n"),
        "full_window_start": _iso_utc(
            _parse_runtime_timestamp(value["full_window_start"], "full_window_start")
        ),
        "full_window_end": _iso_utc(
            _parse_runtime_timestamp(value["full_window_end"], "full_window_end")
        ),
        "canonical_id": _required_text(value["canonical_id"], "canonical_id", 512),
        "dataset_code": _required_text(value["dataset_code"], "dataset_code", 255),
        "family_id": _required_text(value["family_id"], "family_id", 128),
        "family_contract_version": _required_text(
            value["family_contract_version"],
            "family_contract_version",
            64,
        ),
        "data_kind": _required_text(value["data_kind"], "data_kind", 64),
        "frequency": _required_text(value["frequency"], "frequency", 32),
        "source_policy_id": _required_text(value["source_policy_id"], "source_policy_id", 128),
        "instrument_metadata_version": _required_text(
            value["instrument_metadata_version"],
            "instrument_metadata_version",
            128,
        ),
        "query_fingerprint": _required_sha256(
            value["query_fingerprint"],
            "query_fingerprint",
        ),
    }
    if normalized["timeframe_n"] != 1:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    start = _parse_runtime_timestamp(normalized["full_window_start"], "full_window_start")
    end = _parse_runtime_timestamp(normalized["full_window_end"], "full_window_end")
    if start >= end or normalized["data_kind"] != "bars":
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return normalized


def _controlled_artifact_root(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError("artifact_root must be an absolute path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        raise ValueError("artifact_root must be absolute")
    try:
        candidate.mkdir(mode=0o750, parents=True, exist_ok=True)
        root = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("artifact_root is not available") from exc
    if not root.is_dir():
        raise ValueError("artifact_root must be a directory")
    return root


def _safe_artifact_path(root: Path, *, relative_path: str, binding_hash: str) -> Path:
    expected = f"bindings/{_required_sha256(binding_hash, 'binding_hash')}/data.csv"
    if _required_relative_artifact_path(relative_path) != expected:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID")
    candidate = root.joinpath(*relative_path.split("/"))
    _assert_path_contained(root, candidate)
    return candidate


def _required_relative_artifact_path(value: object) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID")
    return value


def _assert_path_contained(root: Path, path: Path) -> None:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID") from exc


def _verify_artifact_file(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    root: Path,
) -> None:
    _assert_path_contained(root, path)
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_PATH_INVALID")
        if metadata.st_size != expected_size:
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_SIZE_MISMATCH")
        with path.open("rb") as handle:
            digest = hashlib.sha256()
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except MarketDataResearchBindingError:
        raise
    except OSError as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_MISSING") from exc
    if digest.hexdigest() != expected_sha256:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_ARTIFACT_DIGEST_MISMATCH")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _csv_required_number(value: object, field_name: str) -> str:
    if value is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OHLC_REQUIRED")
    try:
        return _format_decimal(value, field_name=field_name)
    except MarketDataResearchBindingError as exc:
        if exc.code == "MARKET_DATA_BINDING_NUMERIC_INVALID":
            raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OHLC_REQUIRED") from exc
        raise


def _csv_optional_number(value: object, field_name: str) -> str:
    if value is None:
        return ""
    return _format_decimal(value, field_name=field_name)


def _format_decimal(value: object, *, field_name: str) -> str:
    if isinstance(value, bool):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NUMERIC_INVALID")
    try:
        if isinstance(value, Decimal):
            decimal_value = value
        elif isinstance(value, (int, float, str)):
            if isinstance(value, float) and not math.isfinite(value):
                raise InvalidOperation
            decimal_value = Decimal(str(value).strip())
        else:
            raise InvalidOperation
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NUMERIC_INVALID") from exc
    if not decimal_value.is_finite():
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_NUMERIC_INVALID")
    rendered = format(decimal_value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _aware_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_OBSERVATION_INVALID")
    return value.astimezone(UTC)


def _stored_utc(value: object, field_name: str) -> datetime:
    """Normalize a timestamp read from a timezone-preserving or SQLite column.

    SQLite does not retain a ``timezone=True`` offset.  The platform stores
    every PIT timestamp as UTC, so a naive value returned by SQLite is UTC
    evidence rather than host-local wall time.  Production values still have
    to be real aware datetimes.
    """
    if not isinstance(value, datetime):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_runtime_timestamp(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return _aware_utc(value, field_name)
    if not isinstance(value, str) or not value.strip():
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_RUNTIME_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketDataResearchBindingError(
            "MARKET_DATA_BINDING_RUNTIME_TIMESTAMP_INVALID"
        ) from exc
    return _aware_utc(parsed, field_name)


def _parse_runtime_window_timestamp(
    value: object,
    *,
    field_name: str,
    inclusive_end: bool,
) -> datetime:
    """Parse a runtime unit boundary with the same date-only rule as binding.

    A strategy unit's ordinary ``YYYY-MM-DD`` end is inclusive to users but
    must become the exclusive next UTC midnight at this service boundary.
    Explicit ISO timestamps retain their precise half-open semantics.
    """
    if isinstance(value, str) and len(value.strip()) == 10:
        try:
            parsed_date = date.fromisoformat(value.strip())
        except ValueError as exc:
            raise MarketDataResearchBindingError(
                "MARKET_DATA_BINDING_RUNTIME_TIMESTAMP_INVALID"
            ) from exc
        result = datetime.combine(parsed_date, time.min, tzinfo=UTC)
        return result + timedelta(days=1) if inclusive_end else result
    return _parse_runtime_timestamp(value, field_name)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _trusted_now(clock: Callable[[], datetime]) -> datetime:
    try:
        return _aware_utc(clock(), "clock")
    except MarketDataResearchBindingError as exc:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_CLOCK_INVALID") from exc


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _required_text(value: object, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return normalized


def _required_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return value


def _required_positive_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return value


def _required_nonnegative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_MANIFEST_INVALID")
    return value


def _optional_signing_key(value: str | bytes | None) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, str):
        encoded = value.encode("utf-8") if value else b""
    elif isinstance(value, bytes):
        encoded = value
    else:
        raise TypeError("binding_signing_key must be str, bytes, or None")
    return encoded or None


def _required_signing_key(value: str | bytes) -> bytes:
    normalized = _optional_signing_key(value)
    if normalized is None:
        raise MarketDataResearchBindingError("MARKET_DATA_BINDING_SIGNING_KEY_REQUIRED")
    return normalized


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
