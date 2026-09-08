"""Contracts for the deployment-owned filesystem dataset resolver."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from hashlib import sha256
from pathlib import Path

import pytest

from app.services.research.filesystem_dataset_resolver import FilesystemDatasetObjectResolver


@pytest.mark.asyncio
async def test_filesystem_resolver_persists_real_byte_attestation_across_instances(
    tmp_path: Path,
) -> None:
    """A restart reads a durable receipt and rehashes the controlled source bytes."""

    object_root = tmp_path / "objects"
    receipt_store = tmp_path / "receipts"
    object_root.mkdir()
    receipt_store.mkdir()
    source = object_root / "discovery.parquet"
    payload = b"real controlled dataset bytes\n"
    source.write_bytes(payload)

    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    registered = resolver.import_file(
        user_id="dataset-owner",
        source_path=source,
        partition_kind="DISCOVERY",
    )

    restarted = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    resolved = await restarted.resolve_receipt(
        user_id="dataset-owner",
        receipt_id=registered.receipt_id,
    )
    current = await restarted.resolve_current(
        user_id="dataset-owner",
        logical_object_id=registered.logical_object_id,
    )

    assert resolved.receipt_id == registered.receipt_id
    assert resolved.logical_object_id == registered.logical_object_id
    assert resolved.object_digest == sha256(payload).hexdigest()
    assert resolved.object_size_bytes == len(payload)
    assert resolved.attested_at > registered.attested_at
    assert current.object_digest == resolved.object_digest
    assert current.object_size_bytes == resolved.object_size_bytes
    assert str(source) not in resolved.storage_uri
    assert resolved.storage_uri.startswith("controlled://filesystem/")


@pytest.mark.asyncio
async def test_filesystem_resolver_rejects_replaced_bytes_and_cross_owner_receipt(
    tmp_path: Path,
) -> None:
    """Every resolution reopens the owned file and rejects a replaced inode or owner."""

    object_root, receipt_store, source = _controlled_file(tmp_path, b"original bytes")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    registered = resolver.import_file(
        user_id="dataset-owner",
        source_path=source,
        partition_kind="ITERATION_VALIDATION",
    )

    with pytest.raises(ValueError, match="DATASET_OBJECT_RECEIPT_NOT_FOUND"):
        await resolver.resolve_receipt(user_id="another-owner", receipt_id=registered.receipt_id)

    replacement = object_root / "replacement.parquet"
    replacement.write_bytes(b"original bytes")
    replacement.replace(source)

    with pytest.raises(ValueError, match="DATASET_OBJECT_REVALIDATION_UNAVAILABLE"):
        await resolver.resolve_current(
            user_id="dataset-owner",
            logical_object_id=registered.logical_object_id,
        )
    with pytest.raises(ValueError, match="DATASET_OBJECT_RECEIPT_INVALID") as error:
        await resolver.resolve_receipt(
            user_id="dataset-owner",
            receipt_id=registered.receipt_id,
        )
    assert str(source) not in str(error.value)


def test_filesystem_import_rejects_traversal_symlink_nonregular_oversize_and_sealed(
    tmp_path: Path,
) -> None:
    """The importer accepts only bounded regular files under its configured root."""

    object_root, receipt_store, source = _controlled_file(tmp_path, b"12345")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=4,
    )
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"x")
    nested_outside = tmp_path / "outside-dir"
    nested_outside.mkdir()
    (nested_outside / "secret.parquet").write_bytes(b"x")
    linked_directory = object_root / "linked"
    linked_directory.symlink_to(nested_outside, target_is_directory=True)
    linked_file = object_root / "linked-file.parquet"
    linked_file.symlink_to(outside)
    directory = object_root / "directory.parquet"
    directory.mkdir()
    traversal = directory / ".." / "dataset.parquet"
    group_writable = object_root / "group-writable.parquet"
    group_writable.write_bytes(b"x")
    group_writable.chmod(0o666)
    fifo = object_root / "blocked-reader.fifo"
    os.mkfifo(fifo, 0o600)

    for source_path, expected_code in (
        (source, "DATASET_FILESYSTEM_OBJECT_TOO_LARGE"),
        (outside, "DATASET_FILESYSTEM_SOURCE_DENIED"),
        (linked_directory / "secret.parquet", "DATASET_FILESYSTEM_SOURCE_DENIED"),
        (linked_file, "DATASET_FILESYSTEM_SOURCE_DENIED"),
        (directory, "DATASET_FILESYSTEM_SOURCE_DENIED"),
        (traversal, "DATASET_FILESYSTEM_SOURCE_DENIED"),
        (group_writable, "DATASET_FILESYSTEM_SOURCE_DENIED"),
        (fifo, "DATASET_FILESYSTEM_SOURCE_DENIED"),
    ):
        with pytest.raises(ValueError, match=expected_code):
            resolver.import_file(
                user_id="dataset-owner",
                source_path=source_path,
                partition_kind="DISCOVERY",
            )

    with pytest.raises(ValueError, match="DATASET_FILESYSTEM_PARTITION_DENIED"):
        resolver.import_file(
            user_id="dataset-owner",
            source_path=source,
            partition_kind="SEALED_HOLDOUT",
        )


@pytest.mark.asyncio
async def test_filesystem_resolver_rejects_tampered_persistent_receipt_schema(
    tmp_path: Path,
) -> None:
    """A malformed durable receipt fails closed and never becomes a partial attestation."""

    object_root, receipt_store, source = _controlled_file(tmp_path, b"controlled bytes")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    registered = resolver.import_file(
        user_id="dataset-owner",
        source_path=source,
        partition_kind="FORWARD_OBSERVATION",
    )
    receipt_path = receipt_store / f"{registered.receipt_id}.json"
    record = json.loads(receipt_path.read_text(encoding="utf-8"))
    record["unexpected"] = "tampered"
    receipt_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="DATASET_OBJECT_RECEIPT_INVALID"):
        await FilesystemDatasetObjectResolver(
            object_root=object_root,
            receipt_store=receipt_store,
            max_object_bytes=1024,
        ).resolve_receipt(user_id="dataset-owner", receipt_id=registered.receipt_id)


@pytest.mark.asyncio
async def test_filesystem_resolver_rejects_fifo_receipt_without_blocking(tmp_path: Path) -> None:
    """A named pipe at a known receipt filename is rejected before any blocking read."""

    object_root, receipt_store, source = _controlled_file(tmp_path, b"controlled bytes")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    registered = resolver.import_file(
        user_id="dataset-owner",
        source_path=source,
        partition_kind="DISCOVERY",
    )
    receipt_path = receipt_store / f"{registered.receipt_id}.json"
    receipt_path.unlink()
    os.mkfifo(receipt_path, 0o600)

    with pytest.raises(ValueError, match="DATASET_OBJECT_RECEIPT_INVALID"):
        await resolver.resolve_receipt(user_id="dataset-owner", receipt_id=registered.receipt_id)


@pytest.mark.asyncio
async def test_filesystem_resolver_recovers_only_its_interrupted_link_publication(
    tmp_path: Path,
) -> None:
    """A crash after link-before-unlink leaves one recoverable exact temporary hard link."""

    object_root, receipt_store, source = _controlled_file(tmp_path, b"controlled bytes")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    registered = resolver.import_file(
        user_id="dataset-owner",
        source_path=source,
        partition_kind="DISCOVERY",
    )
    receipt_path = receipt_store / f"{registered.receipt_id}.json"
    interrupted_temporary_path = receipt_store / f".dataset-receipt-{registered.receipt_id}.tmp"
    os.link(receipt_path, interrupted_temporary_path)

    recovered = await FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    ).resolve_receipt(user_id="dataset-owner", receipt_id=registered.receipt_id)

    assert recovered.receipt_id == registered.receipt_id
    assert not interrupted_temporary_path.exists()


@pytest.mark.asyncio
async def test_filesystem_async_resolution_keeps_event_loop_live_and_cancelled_task_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Descriptor hashing runs in a worker thread, so a gate never starves the event loop."""

    object_root, receipt_store, source = _controlled_file(tmp_path, b"controlled bytes")
    resolver = FilesystemDatasetObjectResolver(
        object_root=object_root,
        receipt_store=receipt_store,
        max_object_bytes=1024,
    )
    registered = resolver.import_file(
        user_id="dataset-owner",
        source_path=source,
        partition_kind="DISCOVERY",
    )
    entered_read = threading.Event()
    release_read = threading.Event()
    finished_read = threading.Event()
    original_read = resolver._read_controlled_file

    def gated_read(relative_path: str):
        entered_read.set()
        try:
            if not release_read.wait(timeout=2):
                raise RuntimeError("controlled test gate timed out")
            return original_read(relative_path)
        finally:
            finished_read.set()

    monkeypatch.setattr(resolver, "_read_controlled_file", gated_read)
    resolution = asyncio.create_task(
        resolver.resolve_receipt(user_id="dataset-owner", receipt_id=registered.receipt_id)
    )
    assert await asyncio.to_thread(entered_read.wait, 1)
    heartbeat = asyncio.Event()
    asyncio.get_running_loop().call_soon(heartbeat.set)
    await asyncio.wait_for(heartbeat.wait(), timeout=0.2)
    assert not resolution.done()

    resolution.cancel()
    with pytest.raises(asyncio.CancelledError) as cancellation:
        await resolution
    assert str(cancellation.value) == ""
    release_read.set()
    assert await asyncio.to_thread(finished_read.wait, 1)

    resolved = await resolver.resolve_receipt(
        user_id="dataset-owner",
        receipt_id=registered.receipt_id,
    )
    assert resolved.receipt_id == registered.receipt_id
    assert str(source) not in resolved.storage_uri


def test_filesystem_resolver_rejects_overlapping_or_nonabsolute_control_roots(
    tmp_path: Path,
) -> None:
    """Object bytes and writable receipt manifests must have separate operator-owned roots."""

    object_root = tmp_path / "objects"
    object_root.mkdir()

    with pytest.raises(ValueError, match="DATASET_FILESYSTEM_CONFIGURATION_INVALID"):
        FilesystemDatasetObjectResolver(
            object_root=object_root,
            receipt_store=object_root,
            max_object_bytes=1024,
        )
    with pytest.raises(ValueError, match="DATASET_FILESYSTEM_CONFIGURATION_INVALID"):
        FilesystemDatasetObjectResolver(
            object_root=Path("relative-root"),
            receipt_store=tmp_path,
            max_object_bytes=1024,
        )
    receipt_store = tmp_path / "receipts"
    receipt_store.mkdir()
    object_root.chmod(0o777)
    with pytest.raises(ValueError, match="DATASET_FILESYSTEM_CONFIGURATION_INVALID"):
        FilesystemDatasetObjectResolver(
            object_root=object_root,
            receipt_store=receipt_store,
            max_object_bytes=1024,
        )


def _controlled_file(tmp_path: Path, payload: bytes) -> tuple[Path, Path, Path]:
    object_root = tmp_path / "objects"
    receipt_store = tmp_path / "receipts"
    object_root.mkdir()
    receipt_store.mkdir()
    source = object_root / "dataset.parquet"
    source.write_bytes(payload)
    return object_root, receipt_store, source
