"""Generate or validate Iteration 197's frozen-baseline scope manifest.

The generator is intentionally unable to invent an Iteration 196 baseline.
Pass a reviewed JSON envelope only after Iteration 196 has frozen its relevant
research/backtest contract.  The resulting artifact remains ``provisional``:
it documents the present market-page/API surface but neither enables a feature
flag nor authorizes strategy-page production consumption.

Examples, from ``src/backend``::

    conda run -n base python scripts/generate_iteration197_scope_manifest.py \\
      --iter196-baseline /approved/iter196-market-data-baseline.json \\
      --output /approved/iteration197-scope-manifest.json

    conda run -n base python scripts/generate_iteration197_scope_manifest.py \\
      --validate /approved/iteration197-scope-manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.market_data.scope_manifest import (
    ScopeManifestError,
    build_scope_manifest,
    load_iter196_baseline,
    load_scope_manifest,
    validate_scope_manifest,
    write_scope_manifest,
)


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument(
        "--validate",
        type=Path,
        metavar="MANIFEST",
        help="Validate an existing scope manifest against current checked-out sources.",
    )
    operation.add_argument(
        "--output",
        type=Path,
        metavar="MANIFEST",
        help="Write a newly generated manifest atomically to this existing directory.",
    )
    parser.add_argument(
        "--iter196-baseline",
        type=Path,
        metavar="BASELINE",
        help="Reviewed frozen Iteration 196 baseline envelope; required for generation.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="Repository root whose source surfaces are attested (default: current checkout).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Emit only stable JSON status so a missing baseline cannot look successful."""
    args = _arguments(argv)
    try:
        if args.validate is not None:
            if args.iter196_baseline is not None:
                raise ScopeManifestError("SCOPE_MANIFEST_VALIDATE_BASELINE_UNEXPECTED")
            manifest = load_scope_manifest(args.validate)
            validate_scope_manifest(manifest=manifest, project_root=args.project_root)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "code": "SCOPE_MANIFEST_VALID",
                        "manifest_sha256": manifest["manifest_sha256"],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.iter196_baseline is None:
            raise ScopeManifestError("ITER196_BASELINE_REQUIRED")
        baseline = load_iter196_baseline(args.iter196_baseline)
        manifest = build_scope_manifest(
            project_root=args.project_root,
            iter196_baseline=baseline,
        )
        validate_scope_manifest(manifest=manifest, project_root=args.project_root)
        if args.output is not None:
            write_scope_manifest(manifest=manifest, output_path=args.output)
            payload: dict[str, object] = {
                "status": "ok",
                "code": "SCOPE_MANIFEST_GENERATED",
                "output": str(args.output),
                "manifest_sha256": manifest["manifest_sha256"],
            }
        else:
            # stdout mode is useful for a reviewer to inspect a candidate
            # before deciding whether it belongs in an approved artifact path.
            payload = {"status": "ok", "code": "SCOPE_MANIFEST_GENERATED", "manifest": manifest}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    except ScopeManifestError as exc:
        print(json.dumps({"status": "error", "code": exc.code}, sort_keys=True))
        return 2
    except Exception:
        # File-system and import errors can contain workstation paths.  The
        # manifest is an operator boundary, so keep its public result stable.
        print(json.dumps({"status": "error", "code": "SCOPE_MANIFEST_FAILED"}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
