"""Workspace service subpackage.

This package houses the slices that were extracted out of
:mod:`app.services.workspace_service` (the historical 2.5 kLOC god-class
module). The :class:`app.services.workspace_service.WorkspaceService` facade
keeps its public surface intact and delegates here so external callers do
not need to change.

See ``docs/REFACTORING_BACKLOG.md`` (item 6) for the full migration plan.
"""

from app.services.workspace import reconciliation

__all__ = ["reconciliation"]
