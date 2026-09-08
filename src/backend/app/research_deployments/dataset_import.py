"""Explicit operator-only ingestion command for filesystem dataset receipts.

This module is inert when imported.  Its CLI reads deployment environment
variables through ``Settings(_env_file=None)`` and never reads project ``.env``
files or starts a worker.  It accepts an operator-supplied path only after the
static resolver factory has constrained that path beneath the configured root.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.config import Settings
from app.services.research.dataset_integrity import DatasetObjectAttestation
from app.services.research.filesystem_dataset_resolver import FilesystemDatasetObjectResolver
from app.services.research.resolver_factory import resolve_configured_dataset_object_resolver

_ALLOWED_PARTITIONS = ("DISCOVERY", "ITERATION_VALIDATION", "FORWARD_OBSERVATION")


def import_filesystem_dataset(
    settings: Any,
    *,
    user_id: str,
    source_path: Path | str,
    partition_kind: str,
) -> DatasetObjectAttestation:
    """Create one receipt through the reviewed filesystem backend only."""

    resolver = resolve_configured_dataset_object_resolver(settings)
    if not isinstance(resolver, FilesystemDatasetObjectResolver):
        raise ValueError("DATASET_OBJECT_RESOLVER_UNAVAILABLE")
    return resolver.import_file(
        user_id=user_id,
        source_path=source_path,
        partition_kind=partition_kind,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run explicit controlled-file ingestion and emit only the opaque receipt ID."""

    parser = argparse.ArgumentParser(description="Register a controlled filesystem dataset object")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--partition-kind", required=True, choices=_ALLOWED_PARTITIONS)
    arguments = parser.parse_args(argv)
    try:
        # Explicitly disable BaseSettings' configured .env files.  Operators
        # supply deployment settings through the process environment instead.
        settings = Settings(_env_file=None)
        attestation = import_filesystem_dataset(
            settings,
            user_id=arguments.user_id,
            source_path=arguments.source_path,
            partition_kind=arguments.partition_kind,
        )
    except (OSError, TypeError, ValueError):
        sys.stderr.write("DATASET_IMPORT_FAILED\n")
        return 2
    sys.stdout.write(
        json.dumps({"receipt_id": attestation.receipt_id}, separators=(",", ":")) + "\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through deployment invocation.
    raise SystemExit(main())
