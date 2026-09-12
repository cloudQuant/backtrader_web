"""Server-attested provenance for recoverable AI-research continuations.

Research task and run snapshots live in workspace settings for recovery.  That
storage is intentionally human-readable, but it must not become an authority
for prompt provenance, continuation context, or strategy lineage.  This
module signs the complete server-produced snapshot with a domain-separated key
derived from ``SECRET_KEY``.  Rotating ``SECRET_KEY`` intentionally invalidates
older signatures and makes their continuation sources fail closed.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from app.config import _DEFAULT_SECRETS, get_settings

AI_RESEARCH_PROVENANCE_SCHEMA_VERSION = "ai-research-continuation-provenance-v1"
AI_RESEARCH_PROVENANCE_VERSION_FIELD = "server_provenance_version"
AI_RESEARCH_PROVENANCE_SIGNATURE_FIELD = "server_provenance_signature"
AI_RESEARCH_PAPER_RUNTIME_ANCHOR_FIELD = "ai_research_paper_runtime_anchor"
AI_RESEARCH_PAPER_RUNTIME_ANCHOR_SCHEMA_VERSION = "ai-research-paper-runtime-anchor-v1"
AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_FIELD = "ai_research_live_handoff_unit_anchor"
AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_SCHEMA_VERSION = "ai-research-live-handoff-unit-anchor-v1"
AI_RESEARCH_PAPER_RUNTIME_METRICS_OBSERVATION_FIELD = (
    "ai_research_paper_runtime_metrics_observation"
)
AI_RESEARCH_PAPER_RUNTIME_METRICS_OBSERVATION_SCHEMA_VERSION = (
    "ai-research-paper-runtime-metrics-observation-v1"
)

_PROVENANCE_DOMAIN = b"ai-research-continuation-provenance-v1"
_PAPER_RUNTIME_ANCHOR_DOMAIN = b"ai-research-paper-runtime-anchor-v1"
_LIVE_HANDOFF_UNIT_ANCHOR_DOMAIN = b"ai-research-live-handoff-unit-anchor-v1"
_PAPER_RUNTIME_METRICS_OBSERVATION_DOMAIN = b"ai-research-paper-runtime-metrics-observation-v1"
_STRATEGY_SNAPSHOT_DOMAIN = b"ai-research-server-strategy-snapshot-v1"
_STRATEGY_SNAPSHOT_MARKER_PATTERN = re.compile(
    r"\s*<!-- ai-research-server-snapshot:([A-Za-z0-9_-]+)\.([0-9a-f]{64}) -->"
)
# Every public placeholder accepted by the general application configuration
# is predictable.  Do not limit the provenance fence to the one normally used
# for ``SECRET_KEY``: deployments sometimes copy the JWT placeholder into the
# general secret field while wiring environments.
_PUBLIC_DEFAULT_SECRETS = frozenset(str(secret).strip() for secret in _DEFAULT_SECRETS)
_ProvenanceKind = Literal["run", "task"]


def issue_server_owned_ai_research_strategy_snapshot_marker(
    *,
    user_id: str,
    strategy_id: str,
    run_id: str,
) -> str | None:
    """Return a verified private reservation marker for a strategy snapshot.

    A promoted strategy is written before a paper or live unit can reference
    it.  The marker is persisted in the strategy row at creation time so the
    public strategy API can reject a code/configuration rewrite during that
    otherwise unprotected interval.  Its HMAC binds owner, strategy and run;
    copying a visible marker to another user strategy cannot reserve it.
    """
    envelope = _strategy_snapshot_envelope(
        user_id=user_id,
        strategy_id=strategy_id,
        run_id=run_id,
    )
    key = _strategy_snapshot_key()
    if envelope is None or key is None:
        return None
    signature = _canonical_hmac(key, envelope)
    if signature is None:
        return None
    encoded_run_id = _urlsafe_payload_text({"run_id": envelope["run_id"]})
    if encoded_run_id is None:
        return None
    return f"\n<!-- ai-research-server-snapshot:{encoded_run_id}.{signature} -->"


def is_server_owned_ai_research_strategy_snapshot(
    description: Any,
    *,
    user_id: str,
    strategy_id: str,
) -> bool:
    """Verify whether a persisted strategy row is reserved by the server."""
    if not isinstance(description, str):
        return False
    key = _strategy_snapshot_key()
    if key is None:
        return False
    for match in reversed(list(_STRATEGY_SNAPSHOT_MARKER_PATTERN.finditer(description))):
        payload = _urlsafe_payload_value(match.group(1))
        run_id = _required_text(payload.get("run_id")) if isinstance(payload, Mapping) else ""
        envelope = _strategy_snapshot_envelope(
            user_id=user_id,
            strategy_id=strategy_id,
            run_id=run_id,
        )
        expected = _canonical_hmac(key, envelope) if envelope is not None else None
        if expected is not None and hmac.compare_digest(match.group(2), expected):
            return True
    return False


def strip_server_owned_ai_research_strategy_snapshot_marker(description: Any) -> str | None:
    """Hide a verified-reservation implementation detail from normal responses."""
    if description is None:
        return None
    return _STRATEGY_SNAPSHOT_MARKER_PATTERN.sub("", str(description)).rstrip()


def sign_ai_research_run_record(
    record: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> Any:
    """Return a run record carrying a server-only provenance signature.

    A missing, default, or short secret deliberately produces an unsigned
    record. The writer can still retain history, while every continuation
    reader rejects the record rather than treating a locally predictable key
    as trusted provenance.
    """
    return _signed_model(
        record,
        kind="run",
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field="run_id",
    )


def sign_ai_research_task_snapshot(
    task: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> Any:
    """Return a task snapshot carrying a server-only provenance signature."""
    return _signed_model(
        task,
        kind="task",
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field="task_id",
    )


def verify_ai_research_run_record(
    record: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> bool:
    """Return whether a run record is signed for this owner and container."""
    return _verify_model(
        record,
        kind="run",
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field="run_id",
    )


def verify_ai_research_task_snapshot(
    task: Any,
    *,
    user_id: str,
    workspace_id: str,
) -> bool:
    """Return whether a task snapshot is signed for this owner and container."""
    return _verify_model(
        task,
        kind="task",
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field="task_id",
    )


def issue_ai_research_paper_runtime_anchor(
    *,
    user_id: str,
    research_workspace_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    run_id: str,
    unit: Any,
    workspace_settings: Mapping[str, Any] | None = None,
    include_runtime_snapshot: bool = True,
    runtime_digest_override: str | None = None,
) -> dict[str, Any] | None:
    """Issue the server-only identity anchor for an AI paper-trading unit.

    Runtime snapshots are intentionally mutable by the trading worker.  The
    anchor instead binds the immutable research/run/unit identity that makes a
    worker snapshot eligible for a paper-review decision.  A browser cannot
    forge the signature and public CRUD rejects mutation of an anchored unit.
    """
    runtime_snapshot_digest = None
    if include_runtime_snapshot:
        runtime_snapshot_digest = ai_research_paper_materialized_runtime_digest(
            workspace_unit_runtime_dir(unit)
        )
        if runtime_snapshot_digest is None:
            return None
    envelope = _paper_runtime_anchor_envelope(
        user_id=user_id,
        research_workspace_id=research_workspace_id,
        paper_workspace_id=paper_workspace_id,
        paper_unit_id=paper_unit_id,
        run_id=run_id,
        unit=unit,
        workspace_settings=workspace_settings,
        runtime_digest_override=runtime_digest_override,
        runtime_snapshot_digest=runtime_snapshot_digest,
    )
    key = _paper_runtime_anchor_key()
    if envelope is None or key is None:
        return None
    signature = _canonical_hmac(key, envelope)
    if signature is None:
        return None
    return {**envelope, "signature": signature}


def verify_ai_research_paper_runtime_anchor(
    anchor: Any,
    *,
    user_id: str,
    research_workspace_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    run_id: str,
    unit: Any,
    workspace_settings: Mapping[str, Any] | None = None,
    require_runtime_snapshot: bool = True,
) -> bool:
    """Verify that a paper unit still matches its server-issued identity."""
    if not isinstance(anchor, Mapping):
        return False
    supplied_signature = anchor.get("signature")
    if (
        not isinstance(supplied_signature, str)
        or len(supplied_signature) != 64
        or any(character not in "0123456789abcdef" for character in supplied_signature)
    ):
        return False
    supplied_snapshot_digest = anchor.get("runtime_snapshot_digest")
    if supplied_snapshot_digest is None:
        if require_runtime_snapshot:
            return False
        runtime_snapshot_digest = None
    elif not _is_sha256_digest(supplied_snapshot_digest):
        return False
    elif require_runtime_snapshot:
        runtime_snapshot_digest = ai_research_paper_materialized_runtime_digest(
            workspace_unit_runtime_dir(unit)
        )
        if runtime_snapshot_digest is None:
            return False
    else:
        # A controlled re-materialization will intentionally replace the old
        # runtime directory. Keep the signed snapshot field in the envelope,
        # but defer its filesystem comparison until sync has completed.
        runtime_snapshot_digest = supplied_snapshot_digest
    envelope = _paper_runtime_anchor_envelope(
        user_id=user_id,
        research_workspace_id=research_workspace_id,
        paper_workspace_id=paper_workspace_id,
        paper_unit_id=paper_unit_id,
        run_id=run_id,
        unit=unit,
        workspace_settings=workspace_settings,
        runtime_snapshot_digest=runtime_snapshot_digest,
    )
    key = _paper_runtime_anchor_key()
    if envelope is None or key is None:
        return False
    expected_signature = _canonical_hmac(key, envelope)
    return expected_signature is not None and hmac.compare_digest(
        supplied_signature, expected_signature
    )


def verify_ai_research_paper_runtime_anchor_for_unit(
    anchor: Any,
    *,
    user_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    unit: Any,
    workspace_settings: Mapping[str, Any] | None = None,
    require_runtime_snapshot: bool = True,
) -> bool:
    """Verify an anchor carried by a unit before a runtime worker starts it."""
    if not isinstance(anchor, Mapping):
        return False
    return verify_ai_research_paper_runtime_anchor(
        anchor,
        user_id=user_id,
        research_workspace_id=_required_text(anchor.get("research_workspace_id")),
        paper_workspace_id=paper_workspace_id,
        paper_unit_id=paper_unit_id,
        run_id=_required_text(anchor.get("run_id")),
        unit=unit,
        workspace_settings=workspace_settings,
        require_runtime_snapshot=require_runtime_snapshot,
    )


def issue_ai_research_live_handoff_unit_anchor(
    *,
    user_id: str,
    research_workspace_id: str,
    live_workspace_id: str,
    live_unit_id: str,
    run_id: str,
    source_run_signature: str,
    unit: Any,
) -> dict[str, Any] | None:
    """Issue an immutable server seal for a prepared live-handoff unit.

    The browser is allowed to see handoff lineage, but it must never turn that
    lineage into authority to run a modified live configuration.  This seal
    binds the exact live unit identity and execution configuration to the
    signed source run.  The initial handoff reservation is written before
    this seal so public CRUD cannot race the create-to-seal interval.
    """
    envelope = _live_handoff_unit_anchor_envelope(
        user_id=user_id,
        research_workspace_id=research_workspace_id,
        live_workspace_id=live_workspace_id,
        live_unit_id=live_unit_id,
        run_id=run_id,
        source_run_signature=source_run_signature,
        unit=unit,
    )
    key = _live_handoff_unit_anchor_key()
    if envelope is None or key is None:
        return None
    signature = _canonical_hmac(key, envelope)
    return {**envelope, "signature": signature} if signature is not None else None


def verify_ai_research_live_handoff_unit_anchor(
    anchor: Any,
    *,
    user_id: str,
    research_workspace_id: str,
    live_workspace_id: str,
    live_unit_id: str,
    run_id: str,
    source_run_signature: str,
    unit: Any,
) -> bool:
    """Verify the exact sealed live unit before an internal live start."""
    if not isinstance(anchor, Mapping):
        return False
    supplied_signature = anchor.get("signature")
    if (
        not isinstance(supplied_signature, str)
        or len(supplied_signature) != 64
        or any(character not in "0123456789abcdef" for character in supplied_signature)
    ):
        return False
    envelope = _live_handoff_unit_anchor_envelope(
        user_id=user_id,
        research_workspace_id=research_workspace_id,
        live_workspace_id=live_workspace_id,
        live_unit_id=live_unit_id,
        run_id=run_id,
        source_run_signature=source_run_signature,
        unit=unit,
    )
    key = _live_handoff_unit_anchor_key()
    if envelope is None or key is None:
        return False
    expected = _canonical_hmac(key, envelope)
    return expected is not None and hmac.compare_digest(supplied_signature, expected)


def issue_ai_research_paper_runtime_metrics_observation(
    *,
    user_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    instance_id: str,
    launch_id: str,
    metrics_snapshot: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Attest post-fill metrics to one server-issued paper launch epoch."""
    envelope = _paper_runtime_metrics_observation_envelope(
        user_id=user_id,
        paper_workspace_id=paper_workspace_id,
        paper_unit_id=paper_unit_id,
        instance_id=instance_id,
        launch_id=launch_id,
        metrics_snapshot=metrics_snapshot,
    )
    key = _paper_runtime_metrics_observation_key()
    if envelope is None or key is None:
        return None
    signature = _canonical_hmac(key, envelope)
    return {**envelope, "signature": signature} if signature is not None else None


def verify_ai_research_paper_runtime_metrics_observation(
    observation: Any,
    *,
    user_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    instance_id: str,
    launch_id: str,
    metrics_snapshot: Mapping[str, Any],
) -> bool:
    """Verify that current metrics were observed after the current launch."""
    if not isinstance(observation, Mapping):
        return False
    supplied_signature = observation.get("signature")
    if (
        not isinstance(supplied_signature, str)
        or len(supplied_signature) != 64
        or any(character not in "0123456789abcdef" for character in supplied_signature)
    ):
        return False
    envelope = _paper_runtime_metrics_observation_envelope(
        user_id=user_id,
        paper_workspace_id=paper_workspace_id,
        paper_unit_id=paper_unit_id,
        instance_id=instance_id,
        launch_id=launch_id,
        metrics_snapshot=metrics_snapshot,
    )
    key = _paper_runtime_metrics_observation_key()
    if envelope is None or key is None:
        return False
    expected = _canonical_hmac(key, envelope)
    return expected is not None and hmac.compare_digest(supplied_signature, expected)


def _signed_model(
    value: Any,
    *,
    kind: _ProvenanceKind,
    user_id: str,
    workspace_id: str,
    source_id_field: str,
) -> Any:
    payload = _model_payload(value)
    signature = _sign_payload(
        payload,
        kind=kind,
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field=source_id_field,
    )
    updates = {
        AI_RESEARCH_PROVENANCE_VERSION_FIELD: (
            AI_RESEARCH_PROVENANCE_SCHEMA_VERSION if signature is not None else None
        ),
        AI_RESEARCH_PROVENANCE_SIGNATURE_FIELD: signature,
    }
    copier = getattr(value, "model_copy", None)
    if callable(copier):
        return copier(update=updates)
    if isinstance(value, dict):
        return {**value, **updates}
    return value


def _verify_model(
    value: Any,
    *,
    kind: _ProvenanceKind,
    user_id: str,
    workspace_id: str,
    source_id_field: str,
) -> bool:
    payload = _model_payload(value)
    return _verify_payload(
        payload,
        kind=kind,
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field=source_id_field,
    )


def _model_payload(value: Any) -> dict[str, Any]:
    """Serialize a Pydantic record without accepting arbitrary object state."""
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        try:
            payload = dumper(mode="json")
        except (TypeError, ValueError):
            return {}
        return dict(payload) if isinstance(payload, dict) else {}
    return dict(value) if isinstance(value, Mapping) else {}


def _sign_payload(
    payload: Mapping[str, Any],
    *,
    kind: _ProvenanceKind,
    user_id: str,
    workspace_id: str,
    source_id_field: str,
) -> str | None:
    key = _provenance_key()
    envelope = _provenance_envelope(
        payload,
        kind=kind,
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field=source_id_field,
    )
    if key is None or envelope is None:
        return None
    try:
        canonical = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _verify_payload(
    payload: Mapping[str, Any],
    *,
    kind: _ProvenanceKind,
    user_id: str,
    workspace_id: str,
    source_id_field: str,
) -> bool:
    if not payload:
        return False
    if payload.get(AI_RESEARCH_PROVENANCE_VERSION_FIELD) != AI_RESEARCH_PROVENANCE_SCHEMA_VERSION:
        return False
    supplied_signature = payload.get(AI_RESEARCH_PROVENANCE_SIGNATURE_FIELD)
    if (
        not isinstance(supplied_signature, str)
        or len(supplied_signature) != 64
        or any(character not in "0123456789abcdef" for character in supplied_signature)
    ):
        return False
    expected_signature = _sign_payload(
        payload,
        kind=kind,
        user_id=user_id,
        workspace_id=workspace_id,
        source_id_field=source_id_field,
    )
    return expected_signature is not None and hmac.compare_digest(
        supplied_signature,
        expected_signature,
    )


def _provenance_envelope(
    payload: Mapping[str, Any],
    *,
    kind: _ProvenanceKind,
    user_id: str,
    workspace_id: str,
    source_id_field: str,
) -> dict[str, Any] | None:
    owner = _required_text(user_id)
    container_workspace_id = _required_text(workspace_id)
    source_id = _required_text(payload.get(source_id_field))
    record_workspace_id = _required_text(payload.get("research_workspace_id"))
    if (
        not owner
        or not container_workspace_id
        or not source_id
        or not record_workspace_id
        or record_workspace_id != container_workspace_id
    ):
        return None
    record = {
        str(key): value
        for key, value in payload.items()
        if key
        not in {
            AI_RESEARCH_PROVENANCE_VERSION_FIELD,
            AI_RESEARCH_PROVENANCE_SIGNATURE_FIELD,
        }
    }
    return {
        "schema_version": AI_RESEARCH_PROVENANCE_SCHEMA_VERSION,
        "kind": kind,
        "owner_id": owner,
        "workspace_id": container_workspace_id,
        "source_id": source_id,
        "record": record,
    }


def _provenance_key() -> bytes | None:
    """Derive a domain-separated HMAC key from a configured non-default secret.

    ``SECRET_KEY`` must be a private, at-least-32-byte value. The application
    default is public and therefore can never attest continuation provenance;
    operators must configure a secure secret before a persisted source can be
    resumed, promoted to paper trading, or used for a live handoff.
    """
    secret = str(getattr(get_settings(), "SECRET_KEY", "") or "").strip()
    if secret in _PUBLIC_DEFAULT_SECRETS or len(secret.encode("utf-8")) < 32:
        return None
    return hmac.new(secret.encode("utf-8"), _PROVENANCE_DOMAIN, hashlib.sha256).digest()


def _paper_runtime_anchor_key() -> bytes | None:
    """Return a distinct signing key for immutable paper-unit identities."""
    provenance_key = _provenance_key()
    if provenance_key is None:
        return None
    return hmac.new(provenance_key, _PAPER_RUNTIME_ANCHOR_DOMAIN, hashlib.sha256).digest()


def _live_handoff_unit_anchor_key() -> bytes | None:
    provenance_key = _provenance_key()
    if provenance_key is None:
        return None
    return hmac.new(provenance_key, _LIVE_HANDOFF_UNIT_ANCHOR_DOMAIN, hashlib.sha256).digest()


def _paper_runtime_metrics_observation_key() -> bytes | None:
    provenance_key = _provenance_key()
    if provenance_key is None:
        return None
    return hmac.new(
        provenance_key,
        _PAPER_RUNTIME_METRICS_OBSERVATION_DOMAIN,
        hashlib.sha256,
    ).digest()


def _strategy_snapshot_key() -> bytes | None:
    provenance_key = _provenance_key()
    if provenance_key is None:
        return None
    return hmac.new(provenance_key, _STRATEGY_SNAPSHOT_DOMAIN, hashlib.sha256).digest()


def _strategy_snapshot_envelope(
    *,
    user_id: str,
    strategy_id: str,
    run_id: str,
) -> dict[str, str] | None:
    owner = _required_text(user_id)
    strategy = _required_text(strategy_id)
    run = _required_text(run_id)
    if not owner or not strategy or not run:
        return None
    return {
        "schema_version": "ai-research-server-strategy-snapshot-v1",
        "kind": "strategy-snapshot",
        "owner_id": owner,
        "strategy_id": strategy,
        "run_id": run,
    }


def _urlsafe_payload_text(payload: Mapping[str, Any]) -> str | None:
    try:
        encoded = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _urlsafe_payload_value(value: str) -> dict[str, Any] | None:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, binascii.Error):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _paper_runtime_anchor_envelope(
    *,
    user_id: str,
    research_workspace_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    run_id: str,
    unit: Any,
    workspace_settings: Mapping[str, Any] | None,
    runtime_digest_override: str | None = None,
    runtime_snapshot_digest: str | None = None,
) -> dict[str, Any] | None:
    owner = _required_text(user_id)
    research_workspace = _required_text(research_workspace_id)
    paper_workspace = _required_text(paper_workspace_id)
    unit_id = _required_text(paper_unit_id)
    research_run_id = _required_text(run_id)
    if not all((owner, research_workspace, paper_workspace, unit_id, research_run_id)):
        return None
    unit_payload = _model_payload(unit)
    if not unit_payload:
        # Runtime workers hold SQLAlchemy rows rather than Pydantic response
        # models.  Read only the identity fields signed below; arbitrary ORM
        # state must not silently enter the envelope.
        unit_payload = {
            field: getattr(unit, field, None)
            for field in (
                "id",
                "workspace_id",
                "strategy_id",
                "symbol",
                "symbol_name",
                "timeframe",
                "timeframe_n",
                "category",
                "trading_mode",
                "gateway_config",
            )
        }
    if _required_text(unit_payload.get("id")) != unit_id:
        return None
    if _required_text(unit_payload.get("workspace_id")) != paper_workspace:
        return None
    identity = {
        "strategy_id": _required_text(unit_payload.get("strategy_id")),
        "symbol": _required_text(unit_payload.get("symbol")),
        "symbol_name": _required_text(unit_payload.get("symbol_name")),
        "timeframe": _required_text(unit_payload.get("timeframe")),
        "timeframe_n": unit_payload.get("timeframe_n"),
        "category": _required_text(unit_payload.get("category")),
        "trading_mode": _required_text(unit_payload.get("trading_mode")).casefold(),
        "gateway_config": unit_payload.get("gateway_config") or {},
    }
    if not identity["strategy_id"] or not identity["symbol"] or identity["trading_mode"] != "paper":
        return None
    if runtime_digest_override is not None and not _is_sha256_digest(runtime_digest_override):
        return None
    runtime_digest = runtime_digest_override or _paper_runtime_execution_digest(
        unit,
        workspace_settings,
    )
    if runtime_digest is None:
        return None
    if runtime_snapshot_digest is not None and not _is_sha256_digest(runtime_snapshot_digest):
        return None
    envelope = {
        "schema_version": AI_RESEARCH_PAPER_RUNTIME_ANCHOR_SCHEMA_VERSION,
        "kind": "paper-runtime-unit",
        "owner_id": owner,
        "research_workspace_id": research_workspace,
        "paper_workspace_id": paper_workspace,
        "paper_unit_id": unit_id,
        "run_id": research_run_id,
        "identity": identity,
        "runtime_digest": runtime_digest,
    }
    if runtime_snapshot_digest is not None:
        envelope["runtime_snapshot_digest"] = runtime_snapshot_digest
    return envelope


def _live_handoff_unit_anchor_envelope(
    *,
    user_id: str,
    research_workspace_id: str,
    live_workspace_id: str,
    live_unit_id: str,
    run_id: str,
    source_run_signature: str,
    unit: Any,
) -> dict[str, Any] | None:
    owner = _required_text(user_id)
    research_workspace = _required_text(research_workspace_id)
    live_workspace = _required_text(live_workspace_id)
    unit_id = _required_text(live_unit_id)
    research_run_id = _required_text(run_id)
    source_signature = _required_text(source_run_signature)
    if not all(
        (owner, research_workspace, live_workspace, unit_id, research_run_id, source_signature)
    ) or not _is_sha256_digest(source_signature):
        return None
    payload = _unit_payload_for_live_handoff_anchor(unit)
    if (
        payload is None
        or _required_text(payload.get("id")) != unit_id
        or _required_text(payload.get("workspace_id")) != live_workspace
        or _required_text(payload.get("trading_mode")).casefold() != "live"
    ):
        return None
    identity = {
        "strategy_id": _required_text(payload.get("strategy_id")),
        "strategy_name": _required_text(payload.get("strategy_name")),
        "symbol": _required_text(payload.get("symbol")),
        "symbol_name": _required_text(payload.get("symbol_name")),
        "timeframe": _required_text(payload.get("timeframe")),
        "timeframe_n": payload.get("timeframe_n"),
        "category": _required_text(payload.get("category")),
        "trading_mode": "live",
    }
    if not identity["strategy_id"] or not identity["symbol"]:
        return None
    execution_config = {
        field: strip_server_owned_ai_research_keys(payload.get(field) or {})
        for field in (
            "data_config",
            "unit_settings",
            "params",
            "optimization_config",
            "gateway_config",
        )
    }
    config_digest = _canonical_payload_digest(execution_config)
    if config_digest is None:
        return None
    return {
        "schema_version": AI_RESEARCH_LIVE_HANDOFF_UNIT_ANCHOR_SCHEMA_VERSION,
        "kind": "live-handoff-unit",
        "owner_id": owner,
        "research_workspace_id": research_workspace,
        "live_workspace_id": live_workspace,
        "live_unit_id": unit_id,
        "run_id": research_run_id,
        "source_run_signature": source_signature,
        "identity": identity,
        "configuration_digest": config_digest,
    }


def _paper_runtime_metrics_observation_envelope(
    *,
    user_id: str,
    paper_workspace_id: str,
    paper_unit_id: str,
    instance_id: str,
    launch_id: str,
    metrics_snapshot: Mapping[str, Any],
) -> dict[str, Any] | None:
    owner = _required_text(user_id)
    workspace = _required_text(paper_workspace_id)
    unit = _required_text(paper_unit_id)
    instance = _required_text(instance_id)
    try:
        launch = uuid.UUID(_required_text(launch_id)).hex
    except (AttributeError, TypeError, ValueError):
        return None
    metrics = strip_server_owned_ai_research_keys(dict(metrics_snapshot))
    digest = _canonical_payload_digest(metrics)
    if not all((owner, workspace, unit, instance, launch)) or digest is None:
        return None
    return {
        "schema_version": AI_RESEARCH_PAPER_RUNTIME_METRICS_OBSERVATION_SCHEMA_VERSION,
        "kind": "paper-runtime-metrics-observation",
        "owner_id": owner,
        "paper_workspace_id": workspace,
        "paper_unit_id": unit,
        "instance_id": instance,
        "launch_id": launch,
        "metrics_digest": digest,
    }


def _unit_payload_for_live_handoff_anchor(unit: Any) -> dict[str, Any] | None:
    payload = _model_payload(unit)
    if payload:
        return payload
    fields = (
        "id",
        "workspace_id",
        "strategy_id",
        "strategy_name",
        "symbol",
        "symbol_name",
        "timeframe",
        "timeframe_n",
        "category",
        "trading_mode",
        "data_config",
        "unit_settings",
        "params",
        "optimization_config",
        "gateway_config",
        "lock_trading",
        "lock_running",
    )
    return {field: getattr(unit, field, None) for field in fields}


def _paper_runtime_execution_digest(
    unit: Any,
    workspace_settings: Mapping[str, Any] | None,
) -> str | None:
    """Hash the effective, runnable paper configuration without exposing it.

    Unit identity alone cannot detect a source-template or workspace-data
    change. This expected digest is computed from the template sources and
    generated config before sync; the materialized runtime is separately
    compared against it after sync and immediately before process launch.
    Server provenance keys are stripped to avoid a signature/configuration
    cycle and to keep handoff bookkeeping mutable.
    """
    try:
        from app.services import workspace_unit_runtime

        effective_config = workspace_unit_runtime._build_trading_unit_config(
            unit,
            dict(workspace_settings or {}),
        )
        template_dir = workspace_unit_runtime.get_strategy_dir(
            _required_text(getattr(unit, "strategy_id", None))
        )
        payload = {
            "runtime_config": _strip_server_owned_research_keys(effective_config),
            "source_files": _expected_runtime_python_file_digests(template_dir),
        }
        return _canonical_payload_digest(payload)
    except (OSError, TypeError, ValueError):
        return None


def workspace_unit_runtime_dir(unit: Any) -> Path:
    """Resolve the isolated runtime directory for a unit without materializing it."""
    from app.services import workspace_unit_runtime

    return workspace_unit_runtime.unit_dir(
        _required_text(getattr(unit, "workspace_id", None)),
        _required_text(getattr(unit, "id", None)),
    )


def ai_research_paper_materialized_runtime_digest(runtime_dir: Path) -> str | None:
    """Hash exactly the runnable unit files just before process launch.

    The digest intentionally covers only the isolated copied sources and
    config.yaml.  Once materialized, later edits to a shared strategy template
    or workspace settings cannot alter this directory; checking it immediately
    before subprocess creation closes the pre-anchor/template-write race.
    """
    try:
        payload = {
            "runtime_config": _strip_server_owned_research_keys(
                _runtime_config_payload(runtime_dir)
            ),
            "source_files": _runtime_python_file_digests(runtime_dir),
        }
        return _canonical_payload_digest(payload)
    except (OSError, TypeError, ValueError):
        return None


def _expected_runtime_python_file_digests(template_dir: Path) -> dict[str, str]:
    """Return the exact Python source set that runtime sync must copy."""
    digests = _runtime_python_file_digests(template_dir)
    if "run.py" not in digests:
        from app.services import workspace_unit_runtime

        digests["run.py"] = hashlib.sha256(
            workspace_unit_runtime._UNIT_RUN_PY.encode("utf-8")
        ).hexdigest()
    return digests


def _runtime_python_file_digests(template_dir: Path) -> dict[str, str]:
    """Return stable digests of executable Python files in a runtime tree."""
    if not template_dir.is_dir():
        return {}
    digests: dict[str, str] = {}
    for path in sorted(template_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix != ".py":
            continue
        digests[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def _runtime_config_payload(runtime_dir: Path) -> Any:
    """Load the materialized config as data so server-owned keys can be removed."""
    config_path = runtime_dir / "config.yaml"
    if not config_path.is_file():
        return None
    import yaml

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, (dict, list)):
        raise ValueError("paper runtime config is not a structured payload")
    return loaded


def strip_server_owned_ai_research_keys(value: Any) -> Any:
    """Remove server-owned AI-research bookkeeping from an execution payload.

    The paper-runtime digest and live-promotion copier share this rule.  A
    paper unit's anchor, review state and task metadata attest that *paper*
    target only; copying those fields into a live unit would neither preserve
    their meaning nor be safe to treat as executable configuration.
    """
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, nested_value in value.items():
            key = str(raw_key)
            normalized = key.strip().casefold()
            if normalized == "ai_research" or normalized.startswith("ai_research_"):
                continue
            result[key] = strip_server_owned_ai_research_keys(nested_value)
        return result
    if isinstance(value, list):
        return [strip_server_owned_ai_research_keys(item) for item in value]
    if isinstance(value, tuple):
        return [strip_server_owned_ai_research_keys(item) for item in value]
    return value


# Private compatibility alias for existing digest call sites.  New callers use
# the public name above so provenance stripping is not copied inconsistently.
_strip_server_owned_research_keys = strip_server_owned_ai_research_keys


def _canonical_payload_digest(payload: Any) -> str | None:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _is_sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_hmac(key: bytes, envelope: Mapping[str, Any]) -> str | None:
    try:
        canonical = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _required_text(value: Any) -> str:
    return str(value or "").strip()
