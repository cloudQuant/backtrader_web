#!/usr/bin/env python
"""Safe entry point for the SimNow CTP certification workspace."""

from __future__ import annotations

import sys
from pathlib import Path


WORKSPACE_DIR = Path(__file__).resolve().parent
STRATEGIES_DIR = WORKSPACE_DIR.parents[1]
PROJECT_ROOT = STRATEGIES_DIR.parent
if str(STRATEGIES_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGIES_DIR))

from ctp_certification_runner import CertificationWorkspace, main as run_workspace  # noqa: E402


WORKSPACE = CertificationWorkspace(
    label="SimNow CTP simulation",
    suite_dir=WORKSPACE_DIR,
    project_root=PROJECT_ROOT,
    environment_variable="SIMNOW_ENV",
    order_symbol_variable="SIMNOW_ORDER_SYMBOL",
    tick_symbol_variable="SIMNOW_TICK_SYMBOL",
)


def main(argv: list[str] | None = None) -> int:
    """Run the SimNow workspace."""
    return run_workspace(WORKSPACE, argv)


if __name__ == "__main__":
    raise SystemExit(main())
