"""Bounded, event-aware delivery of verified continuity to the lifecycle bridge."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from divineos.runtime import Runtime
from divineos.store import read_connection

PANEL_CHARS = 600
CONTEXT_BYTES = 24_000
STOPWORDS = {
    "about", "after", "again", "and", "are", "for", "from", "have", "into",
    "that", "the", "this", "what", "when", "where", "with", "work", "your",
}


def panels(title: str, content: str) -> list[str]:
    """Keep all text, splitting long paragraphs without dropping their middle."""
    parts: list[str] = []
    for paragraph in content.splitlines():
        if not paragraph.strip():
            continue
        remaining = paragraph
        while remaining:
            if len(remaining) <= PANEL_CHARS:
                parts.append(remaining)
                break
            boundary = remaining.rfind(" ", 0, PANEL_CHARS + 1)
            if boundary < PANEL_CHARS // 2:
                boundary = PANEL_CHARS
            parts.append(remaining[:boundary])
            remaining = remaining[boundary:].lstrip(" ")
    return [f"[{title} {index}/{len(parts)}]\n{part}" for index, part in enumerate(parts, 1)]


def render(groups: list[tuple[str, str]]) -> str:
    result = "\n\n".join(panel for title, content in groups for panel in panels(title, content))
    if len(result.encode("utf-8")) > CONTEXT_BYTES:
        raise RuntimeError("continuity exceeds delivery budget; no partial context delivered")
    return result


def _marker_path(runtime: Runtime, session_id: str) -> Path:
    name = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return runtime.provenance.home / "delivery" / f"{name}.json"


def _marker(runtime: Runtime, session_id: str) -> dict[str, Any] | None:
    path = _marker_path(runtime, session_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _save(runtime: Runtime, session_id: str, state: dict[str, Any]) -> None:
    path = _marker_path(runtime, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".delivery-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(state, output)
        os.replace(temp_name, path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def _words(value: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9]+", value.lower())
        if len(word) > 3 and word not in STOPWORDS
    }


def _verified_update(
    runtime: Runtime, after: int, digest: str
) -> tuple[list[sqlite3.Row], list[sqlite3.Row], int, str]:
    with read_connection(runtime.provenance.database) as conn:
        conn.execute("BEGIN")
        health = runtime._health_on(conn)
        if not health.healthy:
            raise RuntimeError("; ".join(health.messages))
        old = conn.execute("SELECT event_hash FROM events WHERE seq = ?", (after,)).fetchone()
        if not old or old[0] != digest or health.event_count < after:
            raise RuntimeError("delivery position does not match verified history")
        events = conn.execute(
            "SELECT seq, kind, payload_json FROM events WHERE seq > ? ORDER BY seq", (after,)
        ).fetchall()
        memories = conn.execute(
            "SELECT memory_id, text, evidence FROM memories WHERE active = 1 "
            "ORDER BY recorded_at DESC, memory_id"
        ).fetchall()
        head = conn.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()[0]
        return events, memories, health.event_count, head


def deliver(runtime: Runtime, request: dict[str, Any]) -> str | None:
    """Return context, or None when a checked prompt has nothing useful to add."""
    session_id = request["session_id"]
    event = request["hook_event_name"]
    identity = runtime.provenance.repo / "SEREIN.md"
    identity_digest = hashlib.sha256(identity.read_bytes()).hexdigest()
    marker = _marker(runtime, session_id)
    if event == "SessionStart" or marker is None or marker.get("identity") != identity_digest:
        briefing, health = runtime.briefing_result(require_handoff=True)
        if not health.healthy:
            raise RuntimeError("; ".join(m for m in health.messages if m != "HEALTHY"))
        # Verify that the cursor belongs to the same snapshot, not a later write.
        with read_connection(runtime.provenance.database) as conn:
            conn.execute("BEGIN")
            current = runtime._health_on(conn)
            if not current.healthy or current.event_count != health.event_count:
                raise RuntimeError("continuity changed while assembling orientation; retry")
            head = conn.execute(
                "SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()[0]
            delivered_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT memory_id FROM memories WHERE active = 1 "
                    "ORDER BY recorded_at DESC, memory_id LIMIT 5"
                ).fetchall()
            ]
        context = render([("Orientation", briefing)])
        _save(
            runtime,
            session_id,
            {
                "seq": health.event_count,
                "head": head,
                "identity": identity_digest,
                "seen": delivered_ids,
            },
        )
        return context

    seq = marker.get("seq")
    head = marker.get("head")
    seen = marker.get("seen")
    if (
        type(seq) is not int or seq < 1 or not isinstance(head, str)
        or not isinstance(seen, list)
        or not all(isinstance(item, str) for item in seen)
    ):
        raise RuntimeError("delivery marker invalid; remove marker to request full orientation")
    events, memories, count, new_head = _verified_update(runtime, seq, head)
    groups: list[tuple[str, str]] = []
    for row in events:
        payload = json.loads(row["payload_json"])
        if row["kind"] == "memory.recorded":
            groups.append(("New memory", f"{payload['text']} [evidence: {payload['evidence']}]"))
            seen.append(payload["memory_id"])
        elif row["kind"] == "goal.added":
            groups.append(("New goal", payload["text"]))
        elif row["kind"] == "goal.completed":
            groups.append(("Completed goal", payload["text"]))
        elif row["kind"] == "session.handoff":
            groups.append((
                "New handoff",
                f"Next step: {payload['next_step']}. "
                f"Unfinished: {', '.join(payload['unfinished']) or 'none'}. "
                f"Blocked: {', '.join(payload['blocked']) or 'none'}.",
            ))
        else:
            groups.append((
                "History changed",
                f"Verified event {row['seq']}: {row['kind']}. "
                "Run divineos briefing for detail.",
            ))
    terms = _words(request.get("prompt", ""))
    if terms:
        for row in memories:
            if row["memory_id"] in seen:
                continue
            if len(terms & _words(row["text"])) >= 2:
                groups.append(("Relevant memory", f"{row['text']} [evidence: {row['evidence']}]"))
                seen.append(row["memory_id"])
                break
    context = render(groups) if groups else None
    _save(runtime, session_id, {
        "seq": count, "head": new_head, "identity": identity_digest, "seen": seen
    })
    return context
