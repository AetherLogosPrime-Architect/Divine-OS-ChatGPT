"""Preserve host observations without interpreting them as facts or memories."""

from __future__ import annotations

from typing import Any


def validate_observation(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {"source", "request"}:
        raise ValueError("history observation requires source and request")
    if payload["source"] != "codex-hook" or not isinstance(payload["request"], dict):
        raise ValueError("history observation has invalid source or request")
    request = payload["request"]
    for field in ("hook_event_name", "session_id", "cwd"):
        if not isinstance(request.get(field), str) or not request[field].strip():
            raise ValueError(f"history observation requires {field}")
    return payload
