#!/usr/bin/env python3
"""Compare current vs base branch OpenAPI schema for breaking changes.

Detects backward-incompatible API changes by comparing two OpenAPI JSON files:
- Removed endpoints
- Removed required response fields
- Changed endpoint URL paths

Usage:
    python scripts/check_api_compat.py current.json base.json

Exit codes:
    0 - No breaking changes detected
    1 - Breaking changes found
    2 - Input error (missing files, invalid JSON)
"""

import json
import sys
from pathlib import Path
from typing import Any


def load_schema(path: str) -> dict[str, Any]:
    """Load and parse an OpenAPI JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(2)


def get_endpoints(schema: dict[str, Any]) -> set[tuple[str, str]]:
    """Extract all (method, path) pairs from an OpenAPI schema."""
    endpoints = set()
    for path, methods in schema.get("paths", {}).items():
        for method in methods:
            if method.lower() in ("get", "post", "put", "patch", "delete", "head", "options"):
                endpoints.add((method.upper(), path))
    return endpoints


def get_response_fields(
    schema: dict[str, Any], method: str, path: str
) -> dict[str, set[str]]:
    """Extract required response fields for a given endpoint.

    Returns a dict mapping status_code -> set of required field names.
    """
    fields: dict[str, set[str]] = {}
    path_item = schema.get("paths", {}).get(path, {})
    operation = path_item.get(method.lower(), {})
    responses = operation.get("responses", {})

    for status_code, response in responses.items():
        content = response.get("content", {})
        for media_type, media_obj in content.items():
            resp_schema = media_obj.get("schema", {})
            # Resolve $ref if present
            if "$ref" in resp_schema:
                ref_path = resp_schema["$ref"].lstrip("#/").split("/")
                resolved = schema
                for part in ref_path:
                    resolved = resolved.get(part, {})
                resp_schema = resolved
            required = resp_schema.get("required", [])
            properties = resp_schema.get("properties", {})
            field_names = set(required) | set(properties.keys())
            if field_names:
                fields[status_code] = field_names

    return fields


def check_breaking_changes(
    current: dict[str, Any], base: dict[str, Any]
) -> list[str]:
    """Compare schemas and return list of breaking change descriptions."""
    breaking: list[str] = []

    current_endpoints = get_endpoints(current)
    base_endpoints = get_endpoints(base)

    # Check for removed endpoints
    removed = base_endpoints - current_endpoints
    for method, path in sorted(removed):
        breaking.append(f"REMOVED endpoint: {method} {path}")

    # Check for removed required response fields on existing endpoints
    common_endpoints = base_endpoints & current_endpoints
    for method, path in sorted(common_endpoints):
        base_fields = get_response_fields(base, method, path)
        current_fields = get_response_fields(current, method, path)

        for status_code, base_field_set in base_fields.items():
            current_field_set = current_fields.get(status_code, set())
            removed_fields = base_field_set - current_field_set
            if removed_fields:
                breaking.append(
                    f"REMOVED fields in {method} {path} [{status_code}]: "
                    f"{', '.join(sorted(removed_fields))}"
                )

    return breaking


def get_change_summary(
    current: dict[str, Any], base: dict[str, Any]
) -> dict[str, list[str]]:
    """Generate a summary of all API changes (added, removed, modified)."""
    current_endpoints = get_endpoints(current)
    base_endpoints = get_endpoints(base)

    added = sorted(f"{m} {p}" for m, p in (current_endpoints - base_endpoints))
    removed = sorted(f"{m} {p}" for m, p in (base_endpoints - current_endpoints))

    # Detect schema changes on common endpoints
    modified: list[str] = []
    common = base_endpoints & current_endpoints
    for method, path in sorted(common):
        base_op = base.get("paths", {}).get(path, {}).get(method.lower(), {})
        current_op = current.get("paths", {}).get(path, {}).get(method.lower(), {})
        if base_op != current_op:
            modified.append(f"{method} {path}")

    return {"added": added, "removed": removed, "modified": modified}


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python check_api_compat.py <current.json> <base.json>", file=sys.stderr)
        sys.exit(2)

    current_path = sys.argv[1]
    base_path = sys.argv[2]

    current = load_schema(current_path)
    base = load_schema(base_path)

    # Print change summary
    summary = get_change_summary(current, base)
    print("=== API Change Summary ===")
    if summary["added"]:
        print(f"\nAdded endpoints ({len(summary['added'])}):")
        for ep in summary["added"]:
            print(f"  + {ep}")
    if summary["removed"]:
        print(f"\nRemoved endpoints ({len(summary['removed'])}):")
        for ep in summary["removed"]:
            print(f"  - {ep}")
    if summary["modified"]:
        print(f"\nModified endpoints ({len(summary['modified'])}):")
        for ep in summary["modified"]:
            print(f"  ~ {ep}")
    if not any(summary.values()):
        print("\nNo API changes detected.")

    # Check for breaking changes
    breaking = check_breaking_changes(current, base)
    if breaking:
        print(f"\n{'='*50}")
        print(f"BREAKING CHANGES DETECTED ({len(breaking)}):")
        print("=" * 50)
        for change in breaking:
            print(f"  ✗ {change}")
        sys.exit(1)
    else:
        print("\n✓ No breaking changes detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
