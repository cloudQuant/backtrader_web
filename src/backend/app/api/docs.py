"""
API documentation endpoints.

Provides Postman Collection export generated from the OpenAPI schema.
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

POSTMAN_SCHEMA_URL = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def _build_postman_url(server_url: str, path: str) -> dict[str, Any]:
    """Build a Postman URL object from server URL and path.

    Args:
        server_url: Base server URL (e.g. "http://localhost:8000").
        path: API path (e.g. "/api/v1/auth/login").

    Returns:
        Postman URL object with raw, host, and path fields.
    """
    raw = f"{server_url}{path}"
    # Parse host and path parts
    host_part = server_url.rstrip("/")
    path_parts = [p for p in path.split("/") if p]

    return {
        "raw": raw,
        "host": [host_part],
        "path": path_parts,
    }


def _extract_request_body_example(operation: dict[str, Any]) -> dict[str, Any] | None:
    """Extract request body example from an OpenAPI operation.

    Args:
        operation: OpenAPI operation object.

    Returns:
        Postman request body object or None if no body.
    """
    request_body = operation.get("requestBody")
    if not request_body:
        return None

    content = request_body.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})

    # Try to get example from schema
    example = schema.get("example") or schema.get("examples")
    if not example and "properties" in schema:
        # Build example from properties
        example = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if "example" in prop_schema:
                example[prop_name] = prop_schema["example"]
            elif "default" in prop_schema:
                example[prop_name] = prop_schema["default"]

    body: dict[str, Any] = {
        "mode": "raw",
        "raw": "",
        "options": {"raw": {"language": "json"}},
    }

    if example:
        import json

        body["raw"] = json.dumps(example, ensure_ascii=False, indent=2)

    return body


def _extract_response_examples(operation: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract response examples from an OpenAPI operation.

    Args:
        operation: OpenAPI operation object.

    Returns:
        List of Postman response objects.
    """
    import json

    responses = operation.get("responses", {})
    result = []

    for status_code, response_obj in responses.items():
        content = response_obj.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})

        example = schema.get("example") or schema.get("examples")
        body = json.dumps(example, ensure_ascii=False, indent=2) if example else ""

        result.append(
            {
                "name": response_obj.get("description", f"Response {status_code}"),
                "status": str(status_code),
                "body": body,
            }
        )

    return result


def _openapi_to_postman(openapi_schema: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Convert an OpenAPI schema to Postman Collection v2.1 format.

    Args:
        openapi_schema: Full OpenAPI 3.x schema dict.
        base_url: Base URL for the API server.

    Returns:
        Postman Collection v2.1 JSON-serializable dict.
    """
    info = openapi_schema.get("info", {})
    paths = openapi_schema.get("paths", {})

    items: list[dict[str, Any]] = []

    for path, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            operation = path_item.get(method)
            if not operation:
                continue

            # Build operation name
            operation_id = operation.get("operationId", "")
            summary = operation.get("summary", "")
            name = summary or operation_id or f"{method.upper()} {path}"

            # Build request
            request: dict[str, Any] = {
                "method": method.upper(),
                "header": [
                    {"key": "Content-Type", "value": "application/json"},
                    {"key": "Accept", "value": "application/json"},
                ],
                "url": _build_postman_url(base_url, path),
            }

            # Add request body for methods that support it
            if method in ("post", "put", "patch"):
                body = _extract_request_body_example(operation)
                if body:
                    request["body"] = body

            # Build item
            item: dict[str, Any] = {
                "name": name,
                "request": request,
            }

            # Add response examples
            response_examples = _extract_response_examples(operation)
            if response_examples:
                item["response"] = response_examples

            items.append(item)

    collection: dict[str, Any] = {
        "info": {
            "name": info.get("title", "API Collection"),
            "description": info.get("description", ""),
            "version": info.get("version", "1.0.0"),
            "schema": POSTMAN_SCHEMA_URL,
        },
        "item": items,
    }

    return collection


@router.get("/postman", summary="Export Postman Collection")
async def get_postman_collection(request: Request) -> JSONResponse:
    """Generate and return a Postman Collection v2.1 from the OpenAPI schema.

    Reads the application's OpenAPI schema and converts it to Postman Collection
    format, including all endpoints with their URLs, methods, request body
    examples, and response examples.

    Returns:
        JSONResponse with Postman Collection v2.1 JSON.
    """
    openapi_schema = request.app.openapi()

    # Determine base URL from request or OpenAPI servers
    servers = openapi_schema.get("servers", [])
    if servers:
        base_url = servers[0].get("url", "")
    else:
        base_url = str(request.base_url).rstrip("/")

    collection = _openapi_to_postman(openapi_schema, base_url)

    return JSONResponse(content=collection)
