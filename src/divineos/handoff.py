from __future__ import annotations

import json
import sqlite3
from typing import Any


FIELDS = {"completed", "unfinished", "blocked", "decisions", "next_step"}


def validate_handoff(value: Any) -> dict[str, Any]:
    """Validate without rewriting the author's text or silently dropping fields."""

    def text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError(f"handoff requires exactly these fields: {', '.join(sorted(FIELDS))}")
    if not text(value["next_step"]):
        raise ValueError("handoff next_step must be nonempty text")
    for field in ("unfinished", "blocked"):
        if not isinstance(value[field], list) or not all(text(item) for item in value[field]):
            raise ValueError(f"handoff {field} must be a list of nonempty text entries")
    for field, keys in (("completed", {"text", "evidence"}), ("decisions", {"text", "reason"})):
        if not isinstance(value[field], list):
            raise ValueError(f"handoff {field} must be a list")
        for item in value[field]:
            if (
                not isinstance(item, dict)
                or set(item) != keys
                or not all(text(item[key]) for key in keys)
            ):
                raise ValueError(f"handoff {field} entries require nonempty {sorted(keys)}")
    return value


def briefing_handoff(conn: sqlite3.Connection) -> list[str]:
    lines = ["", "## Session handoff"]
    row = conn.execute(
        "SELECT seq, event_id, occurred_at, payload_json FROM events "
        "WHERE kind = 'session.handoff' ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return lines + ["- !!! HANDOFF MISSING: no session checkpoint has been recorded"]
    payload = validate_handoff(json.loads(row["payload_json"]))
    later = conn.execute("SELECT COUNT(*) FROM events WHERE seq > ?", (row["seq"],)).fetchone()[0]
    lines.append(f"- Checkpoint: {row['event_id']} at {row['occurred_at']}")
    if later:
        lines.append(
            f"- !!! HANDOFF HAS LATER ACTIVITY: {later} events recorded after this checkpoint"
        )
    lines.append(
        "- Evidence references are recorded claims; their contents are not rechecked here."
    )
    for field in ("completed", "unfinished", "blocked", "decisions"):
        lines.extend(["", f"### {field.title()}"])
        for item in payload[field]:
            if field == "completed":
                lines.append(f"- {item['text']} [evidence: {item['evidence']}]")
            elif field == "decisions":
                lines.append(f"- {item['text']} [reason: {item['reason']}]")
            else:
                lines.append(f"- {item}")
        if not payload[field]:
            lines.append("- None recorded")
    return lines + ["", "### Next step", payload["next_step"]]
