"""Helpers for safely persisting local files that contain credentials."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_private_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically write text with owner-only permissions.

    The temporary file is created in the target directory with mode ``0600``.
    Replacing the directory entry instead of opening the destination prevents a
    pre-existing symlink from redirecting credential output elsewhere.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding=encoding) as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        target.chmod(0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
