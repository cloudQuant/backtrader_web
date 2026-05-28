#!/usr/bin/env python3
"""Export OpenAPI schema from FastAPI app.

Exports the OpenAPI specification to a JSON file for CI validation,
documentation, and API client generation purposes.

Usage:
    python scripts/export_openapi.py              # exports to openapi.json
    python scripts/export_openapi.py output.json  # exports to custom path
"""

import json
import sys
from pathlib import Path


def export_openapi(output_path: str = "openapi.json") -> Path:
    """Export OpenAPI specification to a JSON file.

    Args:
        output_path: Destination file path. Defaults to 'openapi.json' in cwd.

    Returns:
        Path to the exported file.
    """
    # Add backend source to path
    project_root = Path(__file__).parent.parent / "src" / "backend"
    sys.path.insert(0, str(project_root))

    # Import app after path setup
    from app.main import app

    schema = app.openapi()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)

    print(f"Exported OpenAPI schema: {len(schema.get('paths', {}))} paths")
    print(f"  Version: {schema.get('info', {}).get('version', 'unknown')}")
    print(f"  Output: {out}")

    return out


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    export_openapi(dest)
