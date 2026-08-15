"""Versioned model-card contracts for asset-research promotion governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ModelCard:
    """A concise, immutable challenge record for one prediction head."""

    model_name: str
    head_spec_hash: str
    owner: str
    target_definition: str
    labels: tuple[str, ...]
    training_cutoff_at: datetime
    embargo: str
    baseline_code: str
    evaluation_manifest_hash: str
    limitations: tuple[str, ...]
    failure_modes: tuple[str, ...]
    model_version: str

    def content_hash(self) -> str:
        """Return a stable audit hash for the complete model-card facts."""
        payload = json.dumps(
            {
                "model_name": self.model_name,
                "head_spec_hash": self.head_spec_hash,
                "owner": self.owner,
                "target_definition": self.target_definition,
                "labels": self.labels,
                "training_cutoff_at": self.training_cutoff_at.isoformat(),
                "embargo": self.embargo,
                "baseline_code": self.baseline_code,
                "evaluation_manifest_hash": self.evaluation_manifest_hash,
                "limitations": self.limitations,
                "failure_modes": self.failure_modes,
                "model_version": self.model_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def public_payload(self) -> dict[str, object]:
        """Serialize only non-secret model-card facts."""
        payload = asdict(self)
        payload["content_hash"] = self.content_hash()
        return payload
