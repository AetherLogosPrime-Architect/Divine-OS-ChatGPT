from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from divineos.store import append_event, read_connection, transaction, verify_chain


@dataclass(frozen=True)
class ProjectionState:
    memories: tuple[tuple[str, str, str, str, int], ...]
    goals: tuple[tuple[str, str, str, str, str | None], ...]


def expected_state(database: Path) -> ProjectionState:
    memories: dict[str, tuple[str, str, str, str, int]] = {}
    goals: dict[str, tuple[str, str, str, str, str | None]] = {}
    with read_connection(database) as conn:
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
        memories = tuple(
            tuple(row)
            for row in conn.execute(
                "SELECT memory_id, recorded_at, text, evidence, active "
                "FROM memories ORDER BY memory_id"
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
    if actual_state(database) != expected_state(database):
        return False, "PROJECTION DRIFT: memories/goals do not match the ledger"
    return True, "PROJECTIONS VERIFIED"


def rebuild_projections(database: Path) -> None:
    expected = expected_state(database)
    ok, message, _ = verify_chain(database)
    if not ok:
        raise RuntimeError(f"cannot rebuild from an invalid ledger: {message}")
    with transaction(database) as conn:
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
