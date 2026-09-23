from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from divineos.handoff import briefing_handoff, validate_handoff
from divineos.paths import Provenance, resolve_provenance
from divineos.projections import verify_projections_on
from divineos.store import (
    append_event,
    initialize,
    read_connection,
    transaction,
    verify_chain_on,
    verify_occupant,
)


@dataclass(frozen=True)
class Health:
    healthy: bool
    messages: tuple[str, ...]
    readable: bool
    ledger_message: str
    event_count: int


class Runtime:
    def __init__(self, provenance: Provenance | None = None) -> None:
        self.provenance = provenance or resolve_provenance()

    def initialize(self) -> None:
        identity = self.provenance.repo / "SEREIN.md"
        if not identity.is_file():
            raise RuntimeError(f"IDENTITY MISSING: {identity}")
        if self.provenance.database.exists():
            health = self.health()
            if not health.readable:
                raise RuntimeError(f"INIT REFUSED: {'; '.join(health.messages)}")
            return
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
        database = self.provenance.database
        if not database.is_file():
            return self._unavailable_health()
        try:
            with read_connection(database) as conn:
                conn.execute("BEGIN")
                return self._health_on(conn)
        except sqlite3.Error as exc:
            return self._unavailable_health(exc)

    def _unavailable_health(self, error: sqlite3.Error | None = None) -> Health:
        database = self.provenance.database
        if error is not None and "no such table" in str(error):
            message = f"STATE UNINITIALIZED: schema missing at {database}"
        elif error is not None:
            message = f"STATE STORE UNREADABLE: {database}: {error}"
        elif database.exists():
            message = f"STATE STORE UNREADABLE: {database} is not a file"
        else:
            message = f"STATE STORE MISSING: {database}; use init only for a new home"
        return Health(False, (message,), False, message, 0)

    def _health_on(self, conn: sqlite3.Connection) -> Health:
        messages: list[str] = []
        identity = self.provenance.repo / "SEREIN.md"
        identity_ok = identity.is_file()
        if not identity_ok:
            messages.append(f"IDENTITY MISSING: {identity}")
        ok, ledger_message, event_count = verify_chain_on(conn)
        bound = False
        projections_ok = False
        if not ok:
            messages.append(ledger_message)
        else:
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
        return Health(
            not messages,
            tuple(messages) if messages else ("HEALTHY",),
            readable,
            ledger_message,
            event_count,
        )

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

    def record_handoff(self, payload: object) -> str:
        # Freeze caller-owned containers before validation and the write transaction.
        document = validate_handoff(json.loads(json.dumps(payload)))
        with transaction(self.provenance.database) as conn:
            self._require_write_integrity(conn)
            return append_event(conn, "session.handoff", document)

    def briefing_result(self) -> tuple[str, Health]:
        database = self.provenance.database
        memories: list[sqlite3.Row] = []
        goals: list[sqlite3.Row] = []
        handoff_lines: list[str] = []
        identity_text = ""
        if not database.is_file():
            health = self._unavailable_health()
        else:
            try:
                with read_connection(database) as conn:
                    conn.execute("BEGIN")
                    health = self._health_on(conn)
                    if health.readable:
                        identity_path = self.provenance.repo / "SEREIN.md"
                        try:
                            identity_text = identity_path.read_text(encoding="utf-8")
                            if not identity_text.strip():
                                raise ValueError("identity file is empty")
                        except (OSError, UnicodeError, ValueError) as exc:
                            health = replace(
                                health,
                                healthy=False,
                                readable=False,
                                messages=health.messages
                                + (f"IDENTITY UNREADABLE: {identity_path}: {exc}",),
                            )
                    if health.readable:
                        handoff_lines = briefing_handoff(conn)
                        memories = conn.execute(
                            "SELECT text, evidence FROM memories WHERE active = 1 "
                            "ORDER BY recorded_at DESC LIMIT 5"
                        ).fetchall()
                        goals = conn.execute(
                            "SELECT goal_id, text FROM goals WHERE status = 'active' "
                            "ORDER BY created_at"
                        ).fetchall()
            except sqlite3.Error as exc:
                health = self._unavailable_health(exc)
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
            f"- {health.ledger_message} ({health.event_count} events)",
        ]
        lines.extend(f"- !!! {message}" for message in health.messages if message != "HEALTHY")
        if health.healthy:
            lines.append("- HEALTHY")
        if health.readable:
            lines.extend(
                [
                    "",
                    "## Identity instructions",
                    f"Source: {self.provenance.repo / 'SEREIN.md'} (repository file; outside ledger)",
                    "",
                    identity_text,
                ]
            )
            lines.extend(["", "## Active goals"])
            lines.extend(f"- {row['goal_id'][:8]} — {row['text']}" for row in goals)
            if not goals:
                lines.append("- !!! NO ACTIVE GOAL")
            lines.extend(["", "## Recent memories"])
            lines.extend(f"- {row['text']} [evidence: {row['evidence']}]" for row in memories)
            if not memories:
                lines.append("- !!! MEMORY EMPTY")
            lines.extend(handoff_lines)
        else:
            lines.extend(["", "!!! CONTINUITY WITHHELD: integrity or occupant not verified"])
        return "\n".join(lines), health

    def briefing(self) -> str:
        return self.briefing_result()[0]
