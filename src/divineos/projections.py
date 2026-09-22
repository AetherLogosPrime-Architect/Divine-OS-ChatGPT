from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from divineos.store import (
    append_event,
    read_connection,
    transaction,
    verify_chain,
    verify_chain_on,
    verify_occupant,
)


@dataclass(frozen=True)
class ProjectionState:
    memories: tuple[tuple[str, str, str, str, int], ...]
    goals: tuple[tuple[str, str, str, str, str | None], ...]


def expected_state(database: Path) -> ProjectionState:
    with read_connection(database) as conn:
        return expected_state_on(conn)


def expected_state_on(conn: sqlite3.Connection) -> ProjectionState:
    memories: dict[str, tuple[str, str, str, str, int]] = {}
    goals: dict[str, tuple[str, str, str, str, str | None]] = {}
    events = conn.execute(
        "SELECT occurred_at, kind, payload_json FROM events ORDER BY seq"
    ).fetchall()
    for event in events:
        payload = json.loads(event["payload_json"])
        if event["kind"] == "memory.recorded":
            memory_id = payload["memory_id"]
            memories[memory_id] = (
                memory_id,
                event["occurred_at"],
                payload["text"],
                payload["evidence"],
                1,
            )
        elif event["kind"] == "goal.added":
            goal_id = payload["goal_id"]
            goals[goal_id] = (goal_id, event["occurred_at"], payload["text"], "active", None)
        elif event["kind"] == "goal.completed":
            goal_id = payload["goal_id"]
            existing = goals.get(goal_id)
            if existing is not None:
                goals[goal_id] = (*existing[:3], "done", event["occurred_at"])
    return ProjectionState(
        memories=tuple(sorted(memories.values())),
        goals=tuple(sorted(goals.values())),
    )


def actual_state(database: Path) -> ProjectionState:
    with read_connection(database) as conn:
        return actual_state_on(conn)


def actual_state_on(conn: sqlite3.Connection) -> ProjectionState:
    memories = tuple(
        tuple(row)
        for row in conn.execute(
            "SELECT memory_id, recorded_at, text, evidence, active FROM memories ORDER BY memory_id"
        ).fetchall()
    )
    goals = tuple(
        tuple(row)
        for row in conn.execute(
            "SELECT goal_id, created_at, text, status, completed_at FROM goals ORDER BY goal_id"
        ).fetchall()
    )
    return ProjectionState(memories=memories, goals=goals)


def verify_projections(database: Path) -> tuple[bool, str]:
    ok, message, _ = verify_chain(database)
    if not ok:
        return False, message
    with read_connection(database) as conn:
        return verify_projections_on(conn)


def verify_projections_on(conn: sqlite3.Connection) -> tuple[bool, str]:
    if actual_state_on(conn) != expected_state_on(conn):
        return False, "PROJECTION DRIFT: memories/goals do not match the ledger"
    return True, "PROJECTIONS VERIFIED"


def rebuild_projections(database: Path, *, occupant: str) -> None:
    with transaction(database) as conn:
        ok, message, _ = verify_chain_on(conn)
        if not ok:
            raise RuntimeError(f"cannot rebuild from an invalid ledger: {message}")
        bound, message = verify_occupant(conn, occupant)
        if not bound:
            raise RuntimeError(f"cannot rebuild another occupant's state: {message}")
        expected = expected_state_on(conn)
        conn.execute("DELETE FROM memories")
        conn.execute("DELETE FROM goals")
        conn.executemany(
            "INSERT INTO memories(memory_id, recorded_at, text, evidence, active) "
            "VALUES (?, ?, ?, ?, ?)",
            expected.memories,
        )
        conn.executemany(
            "INSERT INTO goals(goal_id, created_at, text, status, completed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            expected.goals,
        )
        append_event(
            conn,
            "projections.rebuilt",
            {"goals": len(expected.goals), "memories": len(expected.memories)},
        )
