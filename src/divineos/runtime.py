from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from divineos.paths import Provenance, resolve_provenance
from divineos.projections import verify_projections
from divineos.store import append_event, initialize, read_connection, transaction, verify_chain


@dataclass(frozen=True)
class Health:
    healthy: bool
    messages: tuple[str, ...]


class Runtime:
    def __init__(self, provenance: Provenance | None = None) -> None:
        self.provenance = provenance or resolve_provenance()

    def initialize(self) -> None:
        initialize(self.provenance.database)
        with transaction(self.provenance.database) as conn:
            count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            if count == 0:
                append_event(
                    conn,
                    "system.initialized",
                    {"occupant": self.provenance.occupant, "schema": 1},
                )

    def health(self) -> Health:
        messages: list[str] = []
        identity = self.provenance.repo / "SEREIN.md"
        if not identity.is_file():
            messages.append(f"IDENTITY MISSING: {identity}")
        ok, ledger_message, _ = verify_chain(self.provenance.database)
        if not ok:
            messages.append(ledger_message)
        else:
            projections_ok, projection_message = verify_projections(self.provenance.database)
            if not projections_ok:
                messages.append(projection_message)
        with read_connection(self.provenance.database) as conn:
            memory_count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE active = 1"
            ).fetchone()[0]
        if memory_count == 0:
            messages.append("MEMORY EMPTY: record at least one evidence-linked memory")
        return Health(not messages, tuple(messages) if messages else ("HEALTHY",))

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
            append_event(
                conn,
                "memory.recorded",
                {"memory_id": memory_id, "text": clean_text, "evidence": clean_evidence},
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
            append_event(conn, "goal.added", {"goal_id": goal_id, "text": clean})
            conn.execute(
                "INSERT INTO goals(goal_id, created_at, text, status) VALUES (?, ?, ?, 'active')",
                (goal_id, created_at, clean),
            )
        return goal_id

    def complete_goal(self, goal_id: str) -> None:
        with transaction(self.provenance.database) as conn:
            row = conn.execute(
                "SELECT text FROM goals WHERE goal_id = ? AND status = 'active'", (goal_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"active goal not found: {goal_id}")
            completed_at = datetime.now(UTC).isoformat()
            append_event(conn, "goal.completed", {"goal_id": goal_id, "text": row["text"]})
            conn.execute(
                "UPDATE goals SET status = 'done', completed_at = ? WHERE goal_id = ?",
                (completed_at, goal_id),
            )

    def briefing(self) -> str:
        ok, ledger_message, event_count = verify_chain(self.provenance.database)
        with read_connection(self.provenance.database) as conn:
            memories = conn.execute(
                "SELECT text, evidence FROM memories WHERE active = 1 ORDER BY recorded_at DESC LIMIT 5"
            ).fetchall()
            goals = conn.execute(
                "SELECT goal_id, text FROM goals WHERE status = 'active' ORDER BY created_at"
            ).fetchall()
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
        lines.extend(["", "## Active goals"])
        lines.extend(f"- {row['goal_id'][:8]} — {row['text']}" for row in goals)
        if not goals:
            lines.append("- !!! NO ACTIVE GOAL")
        lines.extend(["", "## Recent memories"])
        lines.extend(f"- {row['text']} [evidence: {row['evidence']}]" for row in memories)
        if not memories:
            lines.append("- !!! MEMORY EMPTY")
        return "\n".join(lines)
