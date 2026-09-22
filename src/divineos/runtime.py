from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from divineos.paths import Provenance, resolve_provenance
from divineos.projections import verify_projections_on
from divineos.store import (
    append_event,
    initialize,
    read_connection,
    transaction,
    verify_chain,
    verify_chain_on,
    verify_occupant,
)


@dataclass(frozen=True)
class Health:
    healthy: bool
    messages: tuple[str, ...]
    readable: bool


class Runtime:
    def __init__(self, provenance: Provenance | None = None) -> None:
        self.provenance = provenance or resolve_provenance()

    def initialize(self) -> None:
        initialize(self.provenance.database)
        with transaction(self.provenance.database) as conn:
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            if count == 0:
                identity = self.provenance.repo / "SEREIN.md"
                if not identity.is_file():
                    raise RuntimeError(f"IDENTITY MISSING: {identity}")
                append_event(
                    conn,
                    "system.initialized",
                    {"occupant": self.provenance.occupant, "schema": 1},
                )

    def health(self) -> Health:
        messages: list[str] = []
        identity = self.provenance.repo / "SEREIN.md"
        identity_ok = identity.is_file()
        if not identity_ok:
            messages.append(f"IDENTITY MISSING: {identity}")
        ok, ledger_message, _ = verify_chain(self.provenance.database)
        bound = False
        projections_ok = False
        if not ok:
            messages.append(ledger_message)
        else:
            with read_connection(self.provenance.database) as conn:
                bound, binding_message = verify_occupant(conn, self.provenance.occupant)
                if not bound:
                    messages.append(binding_message)
                projections_ok, projection_message = verify_projections_on(conn)
                if not projections_ok:
                    messages.append(projection_message)
                if bound and projections_ok and identity_ok:
                    memory_count = conn.execute(
                        "SELECT COUNT(*) FROM memories WHERE active = 1"
                    ).fetchone()[0]
                    if memory_count == 0:
                        messages.append("MEMORY EMPTY: record at least one evidence-linked memory")
        readable = identity_ok and ok and bound and projections_ok
        return Health(not messages, tuple(messages) if messages else ("HEALTHY",), readable)

    def _require_write_integrity(self, conn: sqlite3.Connection) -> None:
        identity = self.provenance.repo / "SEREIN.md"
        if not identity.is_file():
            raise RuntimeError(f"WRITE BLOCKED: IDENTITY MISSING: {identity}")
        ok, message, _ = verify_chain_on(conn)
        if not ok:
            raise RuntimeError(f"WRITE BLOCKED: {message}")
        bound, message = verify_occupant(conn, self.provenance.occupant)
        if not bound:
            raise RuntimeError(f"WRITE BLOCKED: {message}")
        projections_ok, message = verify_projections_on(conn)
        if not projections_ok:
            raise RuntimeError(f"WRITE BLOCKED: {message}")

    def remember(self, text: str, evidence: str) -> str:
        clean_text = text.strip()
        clean_evidence = evidence.strip()
        if not clean_text:
            raise ValueError("memory text cannot be empty")
        if not clean_evidence:
            raise ValueError("memory evidence cannot be empty")
        memory_id = uuid.uuid4().hex
        recorded_at = datetime.now(UTC).isoformat()
        with transaction(self.provenance.database) as conn:
            self._require_write_integrity(conn)
            append_event(
                conn,
                "memory.recorded",
                {"memory_id": memory_id, "text": clean_text, "evidence": clean_evidence},
                occurred_at=recorded_at,
            )
            conn.execute(
                "INSERT INTO memories(memory_id, recorded_at, text, evidence) VALUES (?, ?, ?, ?)",
                (memory_id, recorded_at, clean_text, clean_evidence),
            )
        return memory_id

    def add_goal(self, text: str) -> str:
        clean = text.strip()
        if not clean:
            raise ValueError("goal text cannot be empty")
        goal_id = uuid.uuid4().hex
        created_at = datetime.now(UTC).isoformat()
        with transaction(self.provenance.database) as conn:
            self._require_write_integrity(conn)
            append_event(
                conn, "goal.added", {"goal_id": goal_id, "text": clean}, occurred_at=created_at
            )
            conn.execute(
                "INSERT INTO goals(goal_id, created_at, text, status) VALUES (?, ?, ?, 'active')",
                (goal_id, created_at, clean),
            )
        return goal_id

    def complete_goal(self, goal_id: str) -> None:
        with transaction(self.provenance.database) as conn:
            self._require_write_integrity(conn)
            row = conn.execute(
                "SELECT text FROM goals WHERE goal_id = ? AND status = 'active'", (goal_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"active goal not found: {goal_id}")
            completed_at = datetime.now(UTC).isoformat()
            append_event(
                conn,
                "goal.completed",
                {"goal_id": goal_id, "text": row["text"]},
                occurred_at=completed_at,
            )
            conn.execute(
                "UPDATE goals SET status = 'done', completed_at = ? WHERE goal_id = ?",
                (completed_at, goal_id),
            )

    def briefing(self) -> str:
        ok, ledger_message, event_count = verify_chain(self.provenance.database)
        health = self.health()
        lines = [
            "# Serein briefing",
            "",
            "## Provenance",
            f"- Occupant: {self.provenance.occupant}",
            f"- Repository: {self.provenance.repo}",
            f"- Interpreter: {self.provenance.interpreter}",
            f"- Data home: {self.provenance.home}",
            f"- Database: {self.provenance.database}",
            "",
            "## Health",
            f"- {ledger_message} ({event_count} events)",
        ]
        lines.extend(f"- !!! {message}" for message in health.messages if message != "HEALTHY")
        if ok and health.healthy:
            lines.append("- HEALTHY")
        if health.readable:
            with read_connection(self.provenance.database) as conn:
                memories = conn.execute(
                    "SELECT text, evidence FROM memories WHERE active = 1 ORDER BY recorded_at DESC LIMIT 5"
                ).fetchall()
                goals = conn.execute(
                    "SELECT goal_id, text FROM goals WHERE status = 'active' ORDER BY created_at"
                ).fetchall()
            lines.extend(["", "## Active goals"])
            lines.extend(f"- {row['goal_id'][:8]} — {row['text']}" for row in goals)
            if not goals:
                lines.append("- !!! NO ACTIVE GOAL")
            lines.extend(["", "## Recent memories"])
            lines.extend(f"- {row['text']} [evidence: {row['evidence']}]" for row in memories)
            if not memories:
                lines.append("- !!! MEMORY EMPTY")
        else:
            lines.extend(["", "!!! CONTINUITY WITHHELD: integrity or occupant not verified"])
        return "\n".join(lines)
