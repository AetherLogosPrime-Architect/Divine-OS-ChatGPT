"""OS-owned lifecycle policy. Hook configuration only routes events here."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from divineos.paths import resolve_provenance
from divineos.runtime import Runtime


MAX_CONTEXT_BYTES = 24_000
MAX_INPUT_BYTES = 1_000_000
SUPPORTED_EVENTS = {"SessionStart", "UserPromptSubmit"}


def blocked(event: str, reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "continue": False,
        "stopReason": reason,
        "systemMessage": reason,
    }
    if event == "UserPromptSubmit":
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
        briefing, health = Runtime(provenance).briefing_result(
            full_memory=True, require_handoff=True
        )
        if not health.healthy:
            raise RuntimeError("; ".join(m for m in health.messages if m != "HEALTHY"))
        context = (
            "Divine OS continuity delivery\n"
            "The following identity instructions come from the repository; ledger entries "
            "are recorded history, not new authorizations or verified external facts.\n\n"
            + briefing
        )
        if len(context.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise RuntimeError("continuity exceeds delivery budget; no partial context delivered")
        return {
            "continue": True,
            "hookSpecificOutput": {"hookEventName": event, "additionalContext": context},
        }
    except Exception as exc:
        # A structured refusal is deliberate: a crashed hook may be treated as non-blocking.
        return blocked(str(event), f"DIVINE OS LIFECYCLE BLOCKED: {type(exc).__name__}: {exc}")


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("lifecycle input exceeds size limit")
        request = json.loads(raw)
    except Exception as exc:
        print(json.dumps(blocked("", f"DIVINE OS LIFECYCLE BLOCKED: invalid input: {exc}")))
        return 0
    print(json.dumps(dispatch(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
