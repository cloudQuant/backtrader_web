from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_URLOpen = Callable[..., Any]


@dataclass(frozen=True)
class OllamaHealth:
    available: bool
    base_url: str
    models: list[str] = field(default_factory=list)
    error: str | None = None


def check_ollama_health(
    *,
    base_url: str = "http://localhost:11434",
    timeout: float = 2.0,
    urlopen: _URLOpen | None = None,
) -> OllamaHealth:
    opener = urlopen or urllib.request.urlopen
    normalized = base_url.rstrip("/")
    request = urllib.request.Request(f"{normalized}/api/tags", method="GET")
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        return OllamaHealth(available=False, base_url=normalized, error=str(exc))

    models = []
    for item in payload.get("models") or []:
        if isinstance(item, dict) and item.get("name"):
            models.append(str(item["name"]))
    return OllamaHealth(available=True, base_url=normalized, models=models)
