"""
Instance persistence store for live trading instances.

Extracted from LiveTradingManager (123-B) to isolate JSON file I/O
from process management and gateway lifecycle concerns.
"""

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.utils.backend_data_paths import get_backend_data_path

_DATA_DIR = get_backend_data_path()
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"


@contextmanager
def _interprocess_file_lock(lock_file: Path) -> Iterator[None]:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class InstanceStore:
    """JSON-file backed store for live trading instance metadata.

    Thread-safety note: callers must coordinate access externally
    (e.g. via the LiveTradingManager singleton).
    """

    def __init__(self, instances_file: Path | None = None):
        self._file = instances_file or _INSTANCES_FILE

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Hold a cross-process lock for a read-modify-write sequence."""
        with _interprocess_file_lock(self._file.with_suffix(self._file.suffix + ".lock")):
            yield

    # ---- low-level I/O ----

    def load_all(self) -> dict[str, dict[str, Any]]:
        """Load all instances from the JSON file.

        Returns:
            A dictionary of instances keyed by instance ID.
        """
        if self._file.is_file():
            try:
                return json.loads(self._file.read_text("utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                return {}
        return {}

    def save_all(self, data: dict[str, dict[str, Any]]) -> None:
        """Persist all instances to the JSON file.

        Args:
            data: The instances dictionary to save.
        """
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        target = Path(self._file)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).replace(target)

    # ---- convenience helpers ----

    def get(self, instance_id: str) -> dict[str, Any] | None:
        """Get a single instance by ID.

        Args:
            instance_id: The instance ID.

        Returns:
            Instance dict or None.
        """
        return self.load_all().get(instance_id)

    def put(self, instance_id: str, data: dict[str, Any]) -> None:
        """Create or update a single instance.

        Args:
            instance_id: The instance ID.
            data: The instance data to store.
        """
        with self.locked():
            all_instances = self.load_all()
            all_instances[instance_id] = data
            self.save_all(all_instances)

    def delete(self, instance_id: str) -> bool:
        """Remove a single instance.

        Args:
            instance_id: The instance ID.

        Returns:
            True if found and removed, False otherwise.
        """
        with self.locked():
            all_instances = self.load_all()
            if instance_id not in all_instances:
                return False
            del all_instances[instance_id]
            self.save_all(all_instances)
            return True

    def update_fields(self, instance_id: str, **fields: Any) -> dict[str, Any] | None:
        """Update specific fields of an instance.

        Args:
            instance_id: The instance ID.
            **fields: Field names and values to update.

        Returns:
            Updated instance dict or None if not found.
        """
        with self.locked():
            all_instances = self.load_all()
            inst = all_instances.get(instance_id)
            if inst is None:
                return None
            inst.update(fields)
            all_instances[instance_id] = inst
            self.save_all(all_instances)
            return inst
