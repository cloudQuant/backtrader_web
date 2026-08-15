#!/usr/bin/env python3
"""Shared guard for ratchet baseline updates.

Ratchet scripts (large_file / mypy / npm_audit / ...) must refuse ``--update``
unless the caller exports ``ALLOW_BASELINE_UPDATE=1``. CI never injects this
variable, so a baseline refresh has to be a deliberate local act that goes
through review (see ``.github/CODEOWNERS``). This prevents "same-PR baseline
bump" gaming flagged in iteration 193 audit finding C10.

Usage::

    from baseline_update_guard import assert_update_allowed
    if args.update:
        assert_update_allowed("large_file_ratchet")
        write_baseline(...)
"""

from __future__ import annotations

import os
import sys

ENV_VAR = "ALLOW_BASELINE_UPDATE"


def update_allowed() -> bool:
    """Return True only when the env var is explicitly set to ``1``."""
    return os.environ.get(ENV_VAR, "") == "1"


def assert_update_allowed(script_name: str) -> None:
    """Exit with code 2 if the update guard env var is not set.

    Prints a message guiding the caller through the reviewed refresh flow so
    CI failures point at the missing env var rather than silently refreshing.
    """
    if update_allowed():
        return
    print(
        f"{script_name}: refusing --update without {ENV_VAR}=1.\n"
        f"  Baseline refresh must be reviewed (see .github/CODEOWNERS). To run locally:\n"
        f"    ALLOW_BASELINE_UPDATE=1 python3 scripts/ci/{script_name}.py --update\n"
        f"  CI never injects this variable; attach a 'why in-place fix is not "
        f"feasible' note to the PR.",
        file=sys.stderr,
    )
    raise SystemExit(2)
