#!/usr/bin/env python3
"""Check OpenAPI schema for missing example values.

Iterates over all requestBody and responses schemas in the exported
OpenAPI JSON and outputs GitHub Actions warning annotations for any
schema missing `example` or `examples` fields.

This check is non-blocking — it always exits with code 0.

Usage:
    python scripts/check_openapi_examples.py              # checks openapi.json
    python scripts/check_openapi_examples.py schema.json  # checks custom path
"""

import json
import sys
from pathlib import Path


def _has_example(schema: dict) -> bool:
    """Check if a schema object contains example or examples field."""
    if not isinstance(schema, dict):
        return True
    return "example" in schema or "examples" in schema


def _resolve_schema(schema: dict, root: dict) -> dict:
    """Resolve a $ref to the actual schema object."""
    if not isinstance(schema, dict):
        return schema
    ref = schema.get("$ref")
    if ref and ref.startswith("#/"):
        parts = ref.lstrip("#/").split("/")
        resolved = root
        for part in parts:
            resolved = resolved.get(part, {})
        return resolved
    return schema


def _check_schema_for_examples(
    schema: dict, root: dict, location: str, warnings: list[str]
) -> None:
    """Recursively check a schema for example fields.

    Only checks the top-level schema object (not deeply nested properties)
    to keep warnings actionable and focused on request/response bodies.
    """
    resolved = _resolve_schema(schema, root)
    if not isinstance(resolved, dict):
        return

    # Skip if schema is empty or just a reference wrapper
    if not resolved or resolved == {}:
        return

    # Check if the resolved schema has example/examples
    if not _has_example(resolved):
        warnings.append(location)


def check_openapi_examples(schema_path: str = "openapi.json") -> list[str]:
    """Check all requestBody and responses schemas for example fields.

    Args:
        schema_path: Path to the OpenAPI JSON file.

    Returns:
        List of warning messages for schemas missing examples.
    """
    path = Path(schema_path)
    if not path.exists():
        print(f"::warning::OpenAPI schema file not found: {schema_path}")
        return []

    with open(path, encoding="utf-8") as f:
        spec = json.load(f)

    warnings: list[str] = []
    paths = spec.get("paths", {})

    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for method, operation in path_item.items():
            if method in ("parameters", "summary", "description", "servers"):
                continue
            if not isinstance(operation, dict):
                continue

            op_id = operation.get("operationId", f"{method.upper()} {path_str}")

            # Check requestBody
            request_body = operation.get("requestBody")
            if request_body:
                rb_resolved = _resolve_schema(request_body, spec)
                if isinstance(rb_resolved, dict):
                    content = rb_resolved.get("content", {})
                    for media_type, media_obj in content.items():
                        if not isinstance(media_obj, dict):
                            continue
                        schema = media_obj.get("schema", {})
                        resolved_schema = _resolve_schema(schema, spec)
                        if isinstance(resolved_schema, dict) and resolved_schema:
                            if not _has_example(resolved_schema) and not _has_example(
                                media_obj
                            ):
                                location = f"{op_id} - requestBody ({media_type})"
                                warnings.append(location)

            # Check responses
            responses = operation.get("responses", {})
            for status_code, response in responses.items():
                if not isinstance(response, dict):
                    continue
                resp_resolved = _resolve_schema(response, spec)
                if not isinstance(resp_resolved, dict):
                    continue
                content = resp_resolved.get("content", {})
                for media_type, media_obj in content.items():
                    if not isinstance(media_obj, dict):
                        continue
                    schema = media_obj.get("schema", {})
                    resolved_schema = _resolve_schema(schema, spec)
                    if isinstance(resolved_schema, dict) and resolved_schema:
                        if not _has_example(resolved_schema) and not _has_example(
                            media_obj
                        ):
                            location = (
                                f"{op_id} - response {status_code} ({media_type})"
                            )
                            warnings.append(location)

    return warnings


def main() -> None:
    """Main entry point."""
    schema_path = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    warnings = check_openapi_examples(schema_path)

    if warnings:
        print(f"\n⚠ Found {len(warnings)} schema(s) missing example values:\n")
        for w in warnings:
            print(f"::warning::Missing OpenAPI example: {w}")
        print(
            "\n💡 Consider adding 'example' or 'examples' to these schemas "
            "for better API documentation."
        )
    else:
        print("✓ All requestBody and response schemas have example values")

    # Always exit 0 — this check is non-blocking
    sys.exit(0)


if __name__ == "__main__":
    main()
