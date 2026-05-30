"""Sync service support package.

``SyncService`` (in ``app/services/sync_service.py``) is the thin orchestration
facade. The stateless / testable halves live here:

- ``transport``   — mysqldump / mysql / ssh / scp argv + command composition
- ``schema_diff`` — information_schema SQL, summary parsing, schema-delta and
  incremental ALTER synthesis, plus progress-percentage math
- ``progress``    — timestamp/byte formatting, host normalization and history
  file persistence
"""

from app.services.sync import progress, schema_diff, transport

__all__ = ["progress", "schema_diff", "transport"]
