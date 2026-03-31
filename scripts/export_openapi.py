#!/usr/bin/env python3
"""
Export OpenAPI specification to JSON file.

This script exports the FastAPI OpenAPI schema to a JSON file for documentation
and API client generation purposes.

Usage:
    python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path


def export_openapi():
    """Export OpenAPI specification to docs/openapi.json."""
    # Add project root to path
    project_root = Path(__file__).parent.parent / "src" / "backend"
    sys.path.insert(0, str(project_root))

    # Import app after path setup
    from app.main import app

    # Get OpenAPI schema
    openapi_schema = app.openapi()

    # Ensure docs directory exists
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    # Write to file
    output_file = docs_dir / "openapi.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

    print(f"✓ OpenAPI schema exported to {output_file}")
    print(f"  - API Version: {openapi_schema.get('info', {}).get('version', 'unknown')}")
    print(f"  - Endpoints: {len(openapi_schema.get('paths', {}))}")

    return output_file


if __name__ == "__main__":
    export_openapi()
