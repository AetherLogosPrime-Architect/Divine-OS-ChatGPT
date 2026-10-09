"""OS-owned lifecycle policy. Hook configuration only routes events here."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from divineos.delivery import deliver
from divineos.paths import resolve_provenance
from divineos.runtime import Runtime


MAX_INPUT_BYTES = 1_000_000
SUPPORTED_EVENTS = {
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "Stop",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "Interrupt",
}


def blocked(event: str, reason: str) -> dict[str, Any]:
    if event in {"Interrupt", "SessionEnd"}:
        return {"systemMessage": reason}
    if event == "PreToolUse":
        # This event rejects common continuation fields. Including them would
        # cause the host to ignore the intended denial and run the tool anyway.
        return {
            "systemMessage": reason,
            "hookSpecificOutput": {
                "hookEventName": event,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    result: dict[str, Any] = {
        "continue": False,
        "stopReason": reason,
        "systemMessage": reason,
    }
    if event in {"UserPromptSubmit", "PostToolUse"}:
        result.update(decision="block", reason=reason)
    return result


def dispatch(request: object) -> dict[str, Any]:
    event = request.get("hook_event_name", "") if isinstance(request, dict) else ""
    try:
        if not isinstance(request, dict) or event not in SUPPORTED_EVENTS:
            raise ValueError("unsupported or missing lifecycle event")
        if event == "SessionStart" and request.get("source") not in {
            "startup",
            "resume",
            "clear",
            "compact",
        }:
            raise ValueError("unsupported or missing session start source")
        if event == "UserPromptSubmit" and not isinstance(request.get("prompt"), str):
            raise ValueError("missing prompt for relevance check")
        if event in {"PreToolUse", "PostToolUse"}:
            for name in ("tool_name", "tool_use_id"):
                if not isinstance(request.get(name), str) or not request[name].strip():
                    raise ValueError(f"missing {name}")
            if "tool_input" not in request:
                raise ValueError("missing tool_input")
            if event == "PostToolUse" and "tool_response" not in request:
                raise ValueError("missing tool_response")
        if event == "Stop" and (
            "last_assistant_message" not in request
            or request["last_assistant_message"] is not None
            and not isinstance(request["last_assistant_message"], str)
        ):
            raise ValueError("missing or invalid last_assistant_message")
        for name in ("cwd", "session_id"):
            if not isinstance(request.get(name), str) or not request[name].strip():
                raise ValueError(f"missing lifecycle {name}")
        cwd = Path(request["cwd"])
        if not cwd.is_absolute():
            raise ValueError("lifecycle cwd must be absolute")
        configured = os.environ.get("DIVINEOS_HOME", "").strip()
        if not configured or not Path(configured).expanduser().is_absolute():
            raise ValueError("select an existing absolute DIVINEOS_HOME before activation")
        provenance = resolve_provenance(start=cwd)
        source_repo = Path(__file__).resolve().parents[2]
        if provenance.repo != source_repo:
            raise ValueError("loaded OS code and requested repository do not match")
        runtime = Runtime(provenance)
        runtime.record_observation(request)
        if event in {"Interrupt", "SessionEnd", "PreToolUse"}:
            return {}
        if event not in {"SessionStart", "UserPromptSubmit"}:
            return {"continue": True}
        context = deliver(runtime, request)
        if context is None:
            return {"continue": True}
        return {
            "continue": True,
            "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
        }
    except Exception as exc:
        # A structured refusal is deliberate: a crashed hook may be treated as non-blocking.
        return blocked(str(event), f"DIVINE OS LIFECYCLE BLOCKED: {type(exc).__name__}: {exc}")


def invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("lifecycle input exceeds size limit")
        request = json.loads(
            raw,
            parse_constant=invalid_constant,
            object_pairs_hook=unique_fields,
        )
    except Exception as exc:
        # Before parsing we cannot know which event's response shape applies.
        # Exit 2 is the documented blocking/error transport, including tools.
        print(f"DIVINE OS LIFECYCLE BLOCKED: invalid input: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(dispatch(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
