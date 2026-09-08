"""Deployment-owned filesystem resolver for protocol-v2 dataset objects.

This backend deliberately accepts only opaque receipts at API time.  A trusted
deployment operator first registers a regular file below a preconfigured,
service-owned root through :meth:`FilesystemDatasetObjectResolver.import_file`.
The resolver writes an immutable, exclusive receipt manifest outside that root
and reopens/re-hashes the controlled bytes on every lookup.

The filesystem backend is a local trust boundary, not an IAM system.  It pins
the bytes it reads to file descriptors and detects pathname replacement before
returning, then detects later changes at the next resolution.  An administrator
that can replace the configured roots or bypass their ownership/permission
requirements is outside that promise; deployments need OS-level separation for
that stronger threat model.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from app.services.research.dataset_integrity import DatasetObjectAttestation

_ALLOWED_PARTITIONS: Final[frozenset[str]] = frozenset(
    {"DISCOVERY", "ITERATION_VALIDATION", "FORWARD_OBSERVATION"}
)
_RECEIPT_SCHEMA_VERSION: Final[str] = "filesystem-dataset-receipt-v1"
_RECEIPT_SUFFIX: Final[str] = ".json"
_RECEIPT_ID_LENGTH: Final[int] = 64
_MAX_RECEIPT_BYTES: Final[int] = 64 * 1024
_MAX_CONFIGURED_OBJECT_BYTES: Final[int] = 10 * 1024 * 1024 * 1024
_READ_CHUNK_BYTES: Final[int] = 128 * 1024
_RECEIPT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "receipt_id",
        "user_id",
        "logical_object_id",
        "partition_kind",
        "relative_path",
        "object_version",
        "object_digest",
        "object_size_bytes",
        "file_identity",
        "root_fingerprint",
        "attested_at",
        "receipt_hash",
    }
)
_FILE_IDENTITY_FIELDS: Final[frozenset[str]] = frozenset(
    {"device", "inode", "mtime_ns", "ctime_ns", "owner_uid", "mode"}
)


@dataclass(frozen=True, slots=True)
class _ControlledFile:
    """Verified bytes and identity from one descriptor-pinned filesystem read."""

    digest: str
    size_bytes: int
    identity: dict[str, int]


class _FilesystemReadError(Exception):
    """Internal filesystem failure whose public representation is a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FilesystemDatasetObjectResolver:
    """Resolve operator-ingested files under one strictly controlled filesystem root.

    ``object_root`` and ``receipt_store`` must already exist, be distinct,
    non-symlinked absolute directories owned by the service identity, and not
    be group/world writable.  Receipt files are written with ``O_EXCL`` and
    hard-link publication, so this resolver never overwrites a receipt.  The
    store is intentionally separate from imported objects: a principal able to
    write data files cannot forge a receipt merely by creating a JSON manifest.

    There is no cache: every receipt/current lookup reads the manifest and
    streams the current object bytes through SHA-256 again.  File descriptor
    checks narrow local TOCTOU windows, but an OS administrator capable of
    replacing roots or changing ownership after those checks remains outside
    the filesystem-only security guarantee.  POSIX mode/owner checks do not
    inspect extended ACLs; deployments that grant write access through ACLs
    must treat that as outside this backend's trust boundary as well.
    """

    def __init__(
        self,
        *,
        object_root: Path | str,
        receipt_store: Path | str,
        max_object_bytes: int,
    ) -> None:
        self._require_openat_support()
        self._max_object_bytes = self._validate_max_object_bytes(max_object_bytes)
        self._service_uid = os.geteuid()
        self._object_root = self._validate_control_root(object_root)
        self._receipt_store = self._validate_control_root(receipt_store)
        if self._paths_overlap(self._object_root, self._receipt_store):
            raise ValueError("DATASET_FILESYSTEM_CONFIGURATION_INVALID")
        self._object_root_identity = self._trusted_directory_identity(self._object_root)
        self._receipt_store_identity = self._trusted_directory_identity(self._receipt_store)
        self._root_fingerprint = hashlib.sha256(os.fsencode(str(self._object_root))).hexdigest()

    def import_file(
        self,
        *,
        user_id: str,
        source_path: Path | str,
        partition_kind: str,
    ) -> DatasetObjectAttestation:
        """Ingest a deployment-controlled file and create an opaque durable receipt.

        This is deliberately a server/operator API, not a browser-facing file
        upload or path API.  Its ``source_path`` must already be a regular file
        under ``object_root``; callers cannot select arbitrary host paths.
        """

        self._validate_user_id(user_id)
        if partition_kind not in _ALLOWED_PARTITIONS:
            raise ValueError("DATASET_FILESYSTEM_PARTITION_DENIED")
        try:
            relative_path = self._relative_source_path(source_path)
            controlled_file = self._read_controlled_file(relative_path)
        except _FilesystemReadError as exc:
            raise ValueError(exc.code) from None

        for _ in range(8):
            receipt_id = secrets.token_hex(_RECEIPT_ID_LENGTH // 2)
            logical_object_id = f"fsobj-{receipt_id}"
            attested_at = datetime.now(timezone.utc)
            record_without_hash: dict[str, Any] = {
                "schema_version": _RECEIPT_SCHEMA_VERSION,
                "receipt_id": receipt_id,
                "user_id": user_id,
                "logical_object_id": logical_object_id,
                "partition_kind": partition_kind,
                "relative_path": relative_path,
                "object_version": f"filesystem-sha256-{controlled_file.digest}",
                "object_digest": controlled_file.digest,
                "object_size_bytes": controlled_file.size_bytes,
                "file_identity": controlled_file.identity,
                "root_fingerprint": self._root_fingerprint,
                "attested_at": attested_at.isoformat(),
            }
            record = {
                **record_without_hash,
                "receipt_hash": self._record_hash(record_without_hash),
            }
            try:
                self._publish_receipt(receipt_id, record)
            except FileExistsError:
                continue
            except (OSError, TypeError, ValueError):
                raise ValueError("DATASET_FILESYSTEM_RECEIPT_WRITE_FAILED") from None
            return self._record_to_attestation(record, checked_at=attested_at)
        raise ValueError("DATASET_FILESYSTEM_RECEIPT_WRITE_FAILED")

    async def resolve_receipt(
        self,
        *,
        user_id: str,
        receipt_id: str,
    ) -> DatasetObjectAttestation:
        """Resolve one owner-scoped opaque receipt and re-attest its live bytes."""

        return await asyncio.to_thread(self._resolve_receipt_sync, user_id, receipt_id)

    def _resolve_receipt_sync(
        self,
        user_id: str,
        receipt_id: str,
    ) -> DatasetObjectAttestation:
        """Perform descriptor-bound receipt resolution away from the event loop."""

        if not self._valid_receipt_id(receipt_id):
            raise ValueError("DATASET_OBJECT_RECEIPT_NOT_FOUND")
        try:
            record = self._load_receipt(receipt_id)
        except _FilesystemReadError:
            raise ValueError("DATASET_OBJECT_RECEIPT_INVALID") from None
        if record["user_id"] != user_id:
            raise ValueError("DATASET_OBJECT_RECEIPT_NOT_FOUND")
        try:
            controlled_file = self._read_controlled_file(record["relative_path"])
        except _FilesystemReadError:
            raise ValueError("DATASET_OBJECT_RECEIPT_INVALID") from None
        if not self._matches_recorded_object(record, controlled_file):
            raise ValueError("DATASET_OBJECT_RECEIPT_INVALID")
        return self._record_to_attestation(record)

    async def resolve_current(
        self,
        *,
        user_id: str,
        logical_object_id: str,
    ) -> DatasetObjectAttestation:
        """Revalidate the stable filesystem object for a stored snapshot identity."""

        return await asyncio.to_thread(self._resolve_current_sync, user_id, logical_object_id)

    def _resolve_current_sync(
        self,
        user_id: str,
        logical_object_id: str,
    ) -> DatasetObjectAttestation:
        """Perform current-object revalidation away from the event loop."""

        if not isinstance(logical_object_id, str) or not logical_object_id.startswith("fsobj-"):
            raise ValueError("DATASET_OBJECT_REVALIDATION_UNAVAILABLE")
        receipt_id = logical_object_id.removeprefix("fsobj-")
        if not self._valid_receipt_id(receipt_id):
            raise ValueError("DATASET_OBJECT_REVALIDATION_UNAVAILABLE")
        try:
            record = self._load_receipt(receipt_id)
            if record["user_id"] != user_id or record["logical_object_id"] != logical_object_id:
                raise _FilesystemReadError("DATASET_OBJECT_REVALIDATION_UNAVAILABLE")
            controlled_file = self._read_controlled_file(record["relative_path"])
            if not self._matches_recorded_object(record, controlled_file):
                raise _FilesystemReadError("DATASET_OBJECT_REVALIDATION_UNAVAILABLE")
            return self._record_to_attestation(record)
        except (_FilesystemReadError, KeyError, TypeError, ValueError):
            raise ValueError("DATASET_OBJECT_REVALIDATION_UNAVAILABLE") from None

    def _relative_source_path(self, source_path: Path | str) -> str:
        """Return a safe, lexical path relative to the configured object root."""

        try:
            raw_path = Path(source_path)
        except (TypeError, ValueError):
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED") from None
        if not raw_path.is_absolute() or not self._path_components_are_safe(raw_path.parts[1:]):
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
        try:
            relative = raw_path.relative_to(self._object_root)
        except ValueError:
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED") from None
        if not relative.parts or not self._path_components_are_safe(relative.parts):
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
        return "/".join(relative.parts)

    def _read_controlled_file(self, relative_path: str) -> _ControlledFile:
        """Hash a descriptor-pinned controlled file and verify its pathname remains stable."""

        parts = self._parse_relative_path(relative_path)
        try:
            descriptor = self._open_relative_file(parts)
        except OSError:
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED") from None
        try:
            before = os.fstat(descriptor)
            self._validate_source_file_stat(before)
            if before.st_size > self._max_object_bytes:
                raise _FilesystemReadError("DATASET_FILESYSTEM_OBJECT_TOO_LARGE")
            digest = hashlib.sha256()
            size_bytes = 0
            while True:
                chunk = os.read(descriptor, _READ_CHUNK_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > self._max_object_bytes:
                    raise _FilesystemReadError("DATASET_FILESYSTEM_OBJECT_TOO_LARGE")
                digest.update(chunk)
            after = os.fstat(descriptor)
            self._validate_source_file_stat(after)
            if self._source_stat_token(before) != self._source_stat_token(after):
                raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
            if size_bytes != after.st_size:
                raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
            identity = self._file_identity(after)
        except OSError:
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED") from None
        finally:
            os.close(descriptor)

        # Confirm the name still resolves through the non-symlinked tree to the
        # exact inode we just read.  A later replacement will be caught on the
        # next resolution even if it occurs after this final local check.
        try:
            confirmation = self._open_relative_file(parts)
        except OSError:
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED") from None
        try:
            confirmed_stat = os.fstat(confirmation)
            self._validate_source_file_stat(confirmed_stat)
            if self._source_stat_token(confirmed_stat) != self._source_stat_token(after):
                raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
        except OSError:
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED") from None
        finally:
            os.close(confirmation)
        return _ControlledFile(
            digest=digest.hexdigest(),
            size_bytes=size_bytes,
            identity=identity,
        )

    def _open_relative_file(self, parts: tuple[str, ...]) -> int:
        """Open a final file via no-follow directory descriptors rooted at object_root."""

        directory_fd = self._open_trusted_root(self._object_root, self._object_root_identity)
        try:
            for component in parts[:-1]:
                child_fd = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = child_fd
                self._validate_trusted_directory_fd(directory_fd)
            file_fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
        finally:
            os.close(directory_fd)
        return file_fd

    def _publish_receipt(self, receipt_id: str, record: dict[str, Any]) -> None:
        """Atomically publish a new immutable receipt without replace semantics."""

        if not self._valid_receipt_id(receipt_id):
            raise ValueError("invalid receipt id")
        encoded = self._canonical_json(record)
        directory_fd = self._open_trusted_root(self._receipt_store, self._receipt_store_identity)
        temporary_name = f".dataset-receipt-{receipt_id}.tmp"
        final_name = f"{receipt_id}{_RECEIPT_SUFFIX}"
        temporary_created = False
        try:
            temporary_fd = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            temporary_created = True
            try:
                self._write_all(temporary_fd, encoded)
                os.fsync(temporary_fd)
            finally:
                os.close(temporary_fd)
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=directory_fd)
            temporary_created = False
            os.fsync(directory_fd)
        finally:
            if temporary_created:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                except OSError:
                    pass
            os.close(directory_fd)

    def _load_receipt(self, receipt_id: str) -> dict[str, Any]:
        """Read and strictly validate an immutable receipt record from the store."""

        encoded = self._read_receipt_bytes(receipt_id)
        try:
            decoded = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID") from None
        return self._validate_receipt_record(decoded, expected_receipt_id=receipt_id)

    def _read_receipt_bytes(self, receipt_id: str) -> bytes:
        """Read one no-follow receipt file, bounded and pinned to a file descriptor."""

        if not self._valid_receipt_id(receipt_id):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        try:
            directory_fd = self._open_trusted_root(
                self._receipt_store,
                self._receipt_store_identity,
            )
            try:
                descriptor = os.open(
                    f"{receipt_id}{_RECEIPT_SUFFIX}",
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=directory_fd,
                )
                initial_stat = os.fstat(descriptor)
                if initial_stat.st_nlink == 2:
                    self._recover_interrupted_publish(
                        receipt_id,
                        directory_fd,
                        descriptor,
                        initial_stat,
                    )
            finally:
                os.close(directory_fd)
        except (OSError, _FilesystemReadError):
            if "descriptor" in locals():
                os.close(descriptor)
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID") from None
        try:
            before = os.fstat(descriptor)
            self._validate_receipt_file_stat(before)
            if before.st_size > _MAX_RECEIPT_BYTES:
                raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
            chunks: list[bytes] = []
            remaining = _MAX_RECEIPT_BYTES + 1
            while remaining > 0:
                chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            encoded = b"".join(chunks)
            after = os.fstat(descriptor)
            self._validate_receipt_file_stat(after)
            if len(encoded) > _MAX_RECEIPT_BYTES or self._receipt_stat_token(
                before
            ) != self._receipt_stat_token(after):
                raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
            return encoded
        except OSError:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID") from None
        finally:
            os.close(descriptor)

    def _recover_interrupted_publish(
        self,
        receipt_id: str,
        directory_fd: int,
        final_descriptor: int,
        final_stat: os.stat_result,
    ) -> None:
        """Finish a crash-interrupted hard-link publication only when it is provably ours."""

        self._validate_receipt_file_metadata(final_stat)
        if final_stat.st_nlink != 2:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        temporary_name = f".dataset-receipt-{receipt_id}.tmp"
        try:
            temporary_descriptor = os.open(
                temporary_name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory_fd,
            )
        except OSError:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID") from None
        try:
            temporary_stat = os.fstat(temporary_descriptor)
            self._validate_receipt_file_metadata(temporary_stat)
            if temporary_stat.st_nlink != 2 or (temporary_stat.st_dev, temporary_stat.st_ino) != (
                final_stat.st_dev,
                final_stat.st_ino,
            ):
                raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
            os.unlink(temporary_name, dir_fd=directory_fd)
            os.fsync(directory_fd)
            if os.fstat(final_descriptor).st_nlink != 1:
                raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        except OSError:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID") from None
        finally:
            os.close(temporary_descriptor)

    def _validate_receipt_record(
        self, decoded: object, *, expected_receipt_id: str
    ) -> dict[str, Any]:
        """Validate exact receipt schema and its canonical self-hash before use."""

        if not isinstance(decoded, dict) or set(decoded) != _RECEIPT_FIELDS:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        record = dict(decoded)
        if record.get("schema_version") != _RECEIPT_SCHEMA_VERSION:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if record.get("receipt_id") != expected_receipt_id or not self._valid_receipt_id(
            record["receipt_id"]
        ):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if not self._valid_user_id(record.get("user_id")):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if record.get("logical_object_id") != f"fsobj-{expected_receipt_id}":
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if record.get("partition_kind") not in _ALLOWED_PARTITIONS:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        try:
            self._parse_relative_path(record["relative_path"])
        except _FilesystemReadError:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID") from None
        digest = record.get("object_digest")
        if not self._valid_sha256(digest):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if record.get("object_version") != f"filesystem-sha256-{digest}":
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        size = record.get("object_size_bytes")
        if type(size) is not int or size < 0 or size > self._max_object_bytes:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if not self._valid_file_identity(record.get("file_identity")):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        if record.get("root_fingerprint") != self._root_fingerprint:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        attested_at = self._parse_attested_at(record.get("attested_at"))
        if attested_at is None:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        receipt_hash = record.get("receipt_hash")
        if not self._valid_sha256(receipt_hash):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        without_hash = {key: value for key, value in record.items() if key != "receipt_hash"}
        if not secrets.compare_digest(receipt_hash, self._record_hash(without_hash)):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        return record

    def _record_to_attestation(
        self,
        record: dict[str, Any],
        *,
        checked_at: datetime | None = None,
    ) -> DatasetObjectAttestation:
        """Convert a receipt to protocol facts with a fresh successful-check timestamp."""

        receipt_attested_at = self._parse_attested_at(record["attested_at"])
        if receipt_attested_at is None:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")
        attested_at = checked_at or datetime.now(timezone.utc)
        return DatasetObjectAttestation(
            receipt_id=record["receipt_id"],
            user_id=record["user_id"],
            logical_object_id=record["logical_object_id"],
            object_version=record["object_version"],
            object_digest=record["object_digest"],
            object_size_bytes=record["object_size_bytes"],
            storage_uri=f"controlled://filesystem/{record['logical_object_id']}",
            attested_at=attested_at,
        )

    def _matches_recorded_object(
        self,
        record: dict[str, Any],
        controlled_file: _ControlledFile,
    ) -> bool:
        """Compare every byte and immutable identity property recorded at ingestion."""

        return (
            secrets.compare_digest(record["object_digest"], controlled_file.digest)
            and record["object_size_bytes"] == controlled_file.size_bytes
            and record["file_identity"] == controlled_file.identity
        )

    def _open_trusted_root(self, path: Path, expected_identity: tuple[int, int, int]) -> int:
        """Open a configured root without following replacements or symlinks."""

        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            current_identity = self._validate_trusted_directory_fd(descriptor)
            if current_identity != expected_identity:
                raise OSError("controlled root changed")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    def _trusted_directory_identity(self, path: Path) -> tuple[int, int, int]:
        """Validate an initially configured controlled root and return stable identity."""

        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            raise ValueError("DATASET_FILESYSTEM_CONFIGURATION_INVALID") from None
        try:
            return self._validate_trusted_directory_fd(descriptor)
        except (OSError, ValueError):
            raise ValueError("DATASET_FILESYSTEM_CONFIGURATION_INVALID") from None
        finally:
            os.close(descriptor)

    def _validate_trusted_directory_fd(self, descriptor: int) -> tuple[int, int, int]:
        """Require a regular deployment-owned, non-writable-by-others directory."""

        directory_stat = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_uid != self._service_uid
            or directory_stat.st_mode & 0o022
        ):
            raise OSError("untrusted controlled directory")
        return (directory_stat.st_dev, directory_stat.st_ino, directory_stat.st_uid)

    def _validate_source_file_stat(self, source_stat: os.stat_result) -> None:
        """Require one non-linked, deployment-owned regular source file."""

        if (
            not stat.S_ISREG(source_stat.st_mode)
            or source_stat.st_uid != self._service_uid
            or source_stat.st_mode & 0o022
            or source_stat.st_nlink != 1
        ):
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")

    def _validate_receipt_file_stat(self, receipt_stat: os.stat_result) -> None:
        """Require an immutable deployment-owned receipt file before parsing it."""

        self._validate_receipt_file_metadata(receipt_stat)
        if receipt_stat.st_nlink != 1:
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")

    def _validate_receipt_file_metadata(self, receipt_stat: os.stat_result) -> None:
        """Check receipt type, owner, and POSIX mode before considering link count."""

        if (
            not stat.S_ISREG(receipt_stat.st_mode)
            or receipt_stat.st_uid != self._service_uid
            or receipt_stat.st_mode & 0o022
        ):
            raise _FilesystemReadError("DATASET_OBJECT_RECEIPT_INVALID")

    @staticmethod
    def _source_stat_token(
        source_stat: os.stat_result,
    ) -> tuple[int, int, int, int, int, int, int, int]:
        """Return all source fields that must remain unchanged while hashing bytes."""

        return (
            source_stat.st_dev,
            source_stat.st_ino,
            source_stat.st_size,
            source_stat.st_mtime_ns,
            source_stat.st_ctime_ns,
            source_stat.st_uid,
            stat.S_IMODE(source_stat.st_mode),
            source_stat.st_nlink,
        )

    @staticmethod
    def _receipt_stat_token(
        receipt_stat: os.stat_result,
    ) -> tuple[int, int, int, int, int, int, int, int]:
        """Return receipt fields that must remain stable during a bounded read."""

        return FilesystemDatasetObjectResolver._source_stat_token(receipt_stat)

    @staticmethod
    def _file_identity(source_stat: os.stat_result) -> dict[str, int]:
        """Persist source identity sufficient to reject an equal-byte inode replacement."""

        return {
            "device": source_stat.st_dev,
            "inode": source_stat.st_ino,
            "mtime_ns": source_stat.st_mtime_ns,
            "ctime_ns": source_stat.st_ctime_ns,
            "owner_uid": source_stat.st_uid,
            "mode": stat.S_IMODE(source_stat.st_mode),
        }

    @staticmethod
    def _paths_overlap(first: Path, second: Path) -> bool:
        """Return whether two canonical directory roots are equal or nested."""

        try:
            first.relative_to(second)
            return True
        except ValueError:
            pass
        try:
            second.relative_to(first)
            return True
        except ValueError:
            return False

    @staticmethod
    def _path_components_are_safe(parts: tuple[str, ...]) -> bool:
        """Forbid traversal, NULs, separators, and empty components in stored paths."""

        return bool(parts) and all(
            isinstance(part, str)
            and part not in {"", ".", ".."}
            and "\x00" not in part
            and "/" not in part
            and "\\" not in part
            for part in parts
        )

    @classmethod
    def _parse_relative_path(cls, relative_path: object) -> tuple[str, ...]:
        """Decode only a canonical slash-separated relative path from a receipt."""

        if not isinstance(relative_path, str):
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
        parts = tuple(relative_path.split("/"))
        if not cls._path_components_are_safe(parts):
            raise _FilesystemReadError("DATASET_FILESYSTEM_SOURCE_DENIED")
        return parts

    @staticmethod
    def _validate_control_root(value: Path | str) -> Path:
        """Accept only one pre-existing canonical absolute non-symlinked root."""

        try:
            raw_path = Path(value)
            if (
                not raw_path.is_absolute()
                or not FilesystemDatasetObjectResolver._path_components_are_safe(raw_path.parts[1:])
            ):
                raise ValueError("invalid root")
            resolved = raw_path.resolve(strict=True)
            if raw_path != resolved:
                raise ValueError("symlinked root")
            if not resolved.is_dir():
                raise ValueError("not a directory")
            return resolved
        except (OSError, TypeError, ValueError):
            raise ValueError("DATASET_FILESYSTEM_CONFIGURATION_INVALID") from None

    @staticmethod
    def _validate_max_object_bytes(value: int) -> int:
        """Require an explicit bounded object limit rather than an unbounded default."""

        if type(value) is not int or not 0 < value <= _MAX_CONFIGURED_OBJECT_BYTES:
            raise ValueError("DATASET_FILESYSTEM_CONFIGURATION_INVALID")
        return value

    @staticmethod
    def _require_openat_support() -> None:
        """Fail closed when the host cannot enforce no-follow descriptor traversal."""

        if (
            not getattr(os, "O_NOFOLLOW", 0)
            or not getattr(os, "O_DIRECTORY", 0)
            or not getattr(os, "O_NONBLOCK", 0)
        ):
            raise ValueError("DATASET_FILESYSTEM_CONFIGURATION_INVALID")

    @staticmethod
    def _valid_receipt_id(value: object) -> bool:
        """Validate generated opaque receipt IDs before using them as file names."""

        return (
            isinstance(value, str)
            and len(value) == _RECEIPT_ID_LENGTH
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _valid_sha256(value: object) -> bool:
        """Validate a canonical lower-case SHA-256 digest."""

        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _valid_user_id(value: object) -> bool:
        """Keep owner identifiers bounded and nonblank without imposing app-specific syntax."""

        return isinstance(value, str) and bool(value.strip()) and len(value) <= 256

    def _validate_user_id(self, value: object) -> None:
        """Reject malformed server ingestion owner identities."""

        if not self._valid_user_id(value):
            raise ValueError("DATASET_FILESYSTEM_OWNER_DENIED")

    @staticmethod
    def _valid_file_identity(value: object) -> bool:
        """Require an exact, nonnegative integer-only stored source identity."""

        return (
            isinstance(value, dict)
            and set(value) == _FILE_IDENTITY_FIELDS
            and all(type(item) is int and item >= 0 for item in value.values())
        )

    @staticmethod
    def _parse_attested_at(value: object) -> datetime | None:
        """Parse an aware ISO timestamp without accepting a local naive timestamp."""

        if not isinstance(value, str) or len(value) > 128:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _canonical_json(value: dict[str, Any]) -> bytes:
        """Serialize manifest facts deterministically for persistence and self-hashing."""

        return json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def _record_hash(cls, record_without_hash: dict[str, Any]) -> str:
        """Calculate the immutable manifest content hash over all non-hash fields."""

        return hashlib.sha256(cls._canonical_json(record_without_hash)).hexdigest()

    @staticmethod
    def _write_all(descriptor: int, data: bytes) -> None:
        """Write all manifest bytes even if the OS reports a partial write."""

        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("receipt write failed")
            view = view[written:]
