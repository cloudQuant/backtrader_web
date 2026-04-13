"""
Instance persistence store for live trading instances.

Extracted from LiveTradingManager (123-B) to isolate JSON file I/O
from process management and gateway lifecycle concerns.
"""

import json
from pathlib import Path
from typing import Any

from app.utils.backend_data_paths import get_backend_data_path

_DATA_DIR = get_backend_data_path()
_INSTANCES_FILE = _DATA_DIR / "live_trading_instances.json"


class InstanceStore:
    """JSON-file backed store for live trading instance metadata.

    Thread-safety note: callers must coordinate access externally
    (e.g. via the LiveTradingManager singleton).
    """

    def __init__(self, instances_file: Path | None = None):
        self._file = instances_file or _INSTANCES_FILE

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
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

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
        all_instances = self.load_all()
        inst = all_instances.get(instance_id)
        if inst is None:
            return None
        inst.update(fields)
        all_instances[instance_id] = inst
        self.save_all(all_instances)
        return inst
