"""Backend persistent data directory helpers.

This module centralizes backend-owned runtime data under ``src/backend/data``
and migrates legacy files from the repository-root ``data/`` directory.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATION_LOCK = threading.Lock()
_MIGRATION_DONE = False

BACKEND_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LEGACY_BACKEND_DATA_DIR = Path(__file__).resolve().parents[5] / "data"


def _remove_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def _merge_legacy_directory(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            if destination.exists() and not destination.is_dir():
                logger.warning(
                    "Skip migrating legacy backend data directory %s -> %s: destination is not a directory",
                    child,
                    destination,
                )
                continue
            _merge_legacy_directory(child, destination)
            _remove_if_empty(child)
            continue

        if destination.exists():
            try:
                if destination.read_bytes() == child.read_bytes():
                    child.unlink()
                    continue
            except OSError:
                logger.warning(
                    "Skip migrating legacy backend data file %s -> %s: destination already exists",
                    child,
                    destination,
                )
                continue

            logger.warning(
                "Skip migrating legacy backend data file %s -> %s: destination already exists",
                child,
                destination,
            )
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(child), str(destination))

    _remove_if_empty(source)


def ensure_backend_data_dir() -> Path:
    """Return the backend runtime data directory and migrate legacy data if needed."""
    global _MIGRATION_DONE

    with _MIGRATION_LOCK:
        if _MIGRATION_DONE:
            BACKEND_DATA_DIR.mkdir(parents=True, exist_ok=True)
            return BACKEND_DATA_DIR

        BACKEND_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if LEGACY_BACKEND_DATA_DIR.exists() and LEGACY_BACKEND_DATA_DIR != BACKEND_DATA_DIR:
            _merge_legacy_directory(LEGACY_BACKEND_DATA_DIR, BACKEND_DATA_DIR)
            _remove_if_empty(LEGACY_BACKEND_DATA_DIR)

        _MIGRATION_DONE = True
        return BACKEND_DATA_DIR


def get_backend_data_path(*parts: str) -> Path:
    """Build a path under the backend runtime data directory."""
    return ensure_backend_data_dir().joinpath(*parts)
