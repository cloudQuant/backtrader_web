"""Gate the Iteration 197 CFFEX settlement collector candidate.

The candidate has no public request-time route and this operator entrypoint is
intentionally inert by default.  It never imports AkShare, opens a database,
or contacts a provider unless a future approved scheduler supplies the exact
frozen target map, source authorization, and ``--live`` flag to the collector
service.  Keeping this command as a fail-closed gate prevents a developer's
local shell invocation from silently creating a network fetch or a partial
legacy-table import.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

_NOT_RUN_CODE = "CFFEX_SETTLEMENT_LIVE_CONFIRMATION_REQUIRED"
_LIVE_WIRING_CODE = "CFFEX_SETTLEMENT_LIVE_SCHEDULER_WIRING_REQUIRED"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gate the internal Iteration 197 CFFEX settlement batch collector."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Acknowledge that a future approved scheduler may perform provider I/O.",
    )
    return parser


def _emit(payload: dict[str, object], *, stream: TextIO) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def main(argv: Sequence[str] | None = None, *, stream: TextIO | None = None) -> int:
    """Emit a machine-readable fail-closed status without touching external state.

    ``--live`` alone remains insufficient on purpose: a scheduler must first
    resolve explicit CFFEX contracts, authorize the exact source descriptor,
    and invoke :class:`CffexSettlementCollector` directly.  This avoids a CLI
    becoming an alternate, unaudited public execution path.
    """
    arguments = _parser().parse_args(argv)
    output = stream or sys.stdout
    if not arguments.live:
        _emit(
            {
                "status": "NOT_RUN",
                "code": _NOT_RUN_CODE,
                "network_called": False,
                "database_written": False,
            },
            stream=output,
        )
        return 0

    _emit(
        {
            "status": "BLOCKED",
            "code": _LIVE_WIRING_CODE,
            "network_called": False,
            "database_written": False,
        },
        stream=output,
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised as a module command.
    raise SystemExit(main())
