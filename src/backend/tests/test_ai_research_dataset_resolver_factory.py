"""Configuration contracts for the deployment-owned dataset resolver factory."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.research_deployments import dataset_import
from app.research_deployments.dataset_import import import_filesystem_dataset
from app.services.research.dataset_integrity import DatasetObjectAttestation
from app.services.research.filesystem_dataset_resolver import FilesystemDatasetObjectResolver
from app.services.research.resolver_factory import resolve_configured_dataset_object_resolver


def test_resolver_factory_is_disabled_until_an_exact_filesystem_backend_is_configured() -> None:
    """An empty deployment setting remains fail-closed rather than using a fixture backend."""

    assert resolve_configured_dataset_object_resolver(_settings()) is None


def test_resolver_factory_allows_only_static_filesystem_backend(tmp_path: Path) -> None:
    """The factory has no dynamic import or client-controlled backend selection surface."""

    object_root, receipt_store = _roots(tmp_path)
    resolver = resolve_configured_dataset_object_resolver(
        _settings(
            resolver_type="filesystem",
            object_root=str(object_root),
            receipt_store=str(receipt_store),
            max_bytes=1024,
        )
    )

    assert isinstance(resolver, FilesystemDatasetObjectResolver)

    for settings, expected_code in (
        (_settings(resolver_type="inmemory"), "DATASET_OBJECT_RESOLVER_TYPE_DENIED"),
        (
            _settings(
                resolver_type="filesystem",
                object_root="relative-root",
                receipt_store=str(receipt_store),
                max_bytes=1024,
            ),
            "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID",
        ),
        (
            _settings(
                resolver_type="filesystem",
                object_root=str(object_root),
                receipt_store=str(object_root),
                max_bytes=1024,
            ),
            "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID",
        ),
        (
            _settings(
                resolver_type="filesystem",
                object_root=str(object_root),
                receipt_store=str(receipt_store),
                max_bytes=0,
            ),
            "DATASET_OBJECT_RESOLVER_CONFIGURATION_INVALID",
        ),
    ):
        with pytest.raises(ValueError, match=expected_code) as error:
            resolve_configured_dataset_object_resolver(settings)
        assert str(object_root) not in str(error.value)
        assert str(receipt_store) not in str(error.value)


def test_operator_import_helper_reads_only_factory_controlled_real_file(tmp_path: Path) -> None:
    """The deployment helper receives a source path only after static config resolves."""

    object_root, receipt_store = _roots(tmp_path)
    source = object_root / "dataset.parquet"
    source.write_bytes(b"operator-ingested controlled bytes")
    settings = _settings(
        resolver_type="filesystem",
        object_root=str(object_root),
        receipt_store=str(receipt_store),
        max_bytes=1024,
    )

    result = import_filesystem_dataset(
        settings,
        user_id="dataset-owner",
        source_path=source,
        partition_kind="DISCOVERY",
    )

    assert result.receipt_id
    assert (receipt_store / f"{result.receipt_id}.json").is_file()


def test_dataset_import_cli_disables_dotenv_and_emits_only_opaque_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The explicit CLI consumes process settings, not a project .env or storage URI."""

    seen: dict[str, object] = {}

    class _EnvironmentOnlySettings:
        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

    attestation = DatasetObjectAttestation(
        receipt_id="a" * 64,
        user_id="dataset-owner",
        logical_object_id="fsobj-opaque",
        object_version="filesystem-sha256-" + "d" * 64,
        object_digest="d" * 64,
        object_size_bytes=1,
        storage_uri="controlled://filesystem/fsobj-opaque",
        attested_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(dataset_import, "Settings", _EnvironmentOnlySettings)
    monkeypatch.setattr(
        dataset_import, "import_filesystem_dataset", lambda *_args, **_kwargs: attestation
    )

    exit_code = dataset_import.main(
        [
            "--user-id",
            "dataset-owner",
            "--source-path",
            "/deployment-root/dataset.parquet",
            "--partition-kind",
            "DISCOVERY",
        ]
    )

    assert exit_code == 0
    assert seen == {"_env_file": None}
    assert capsys.readouterr().out == '{"receipt_id":"' + "a" * 64 + '"}\n'


def _settings(
    *,
    resolver_type: str = "",
    object_root: str = "",
    receipt_store: str = "",
    max_bytes: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        AI_RESEARCH_PROTOCOL_V2_DATASET_OBJECT_RESOLVER_TYPE=resolver_type,
        AI_RESEARCH_PROTOCOL_V2_DATASET_FILESYSTEM_ROOT=object_root,
        AI_RESEARCH_PROTOCOL_V2_DATASET_RECEIPT_STORE=receipt_store,
        AI_RESEARCH_PROTOCOL_V2_DATASET_MAX_BYTES=max_bytes,
    )


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    object_root = tmp_path / "objects"
    receipt_store = tmp_path / "receipts"
    object_root.mkdir()
    receipt_store.mkdir()
    return object_root, receipt_store
