from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


GENESIS_HASH = "0" * 64


def connect(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def read_connection(database: Path) -> Iterator[sqlite3.Connection]:
    conn = connect(database)
    try:
        yield conn
    finally:
        conn.close()


def initialize(database: Path) -> None:
    with read_connection(database) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                occurred_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                recorded_at TEXT NOT NULL,
                text TEXT NOT NULL,
                evidence TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS goals (
                goal_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('active', 'done')),
                completed_at TEXT
            );
            """
        )


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_hash(
    *, event_id: str, occurred_at: str, kind: str, payload_json: str, prev_hash: str
) -> str:
    material = "\x1f".join((event_id, occurred_at, kind, payload_json, prev_hash))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@contextmanager
def transaction(database: Path) -> Iterator[sqlite3.Connection]:
    initialize(database)
    conn = connect(database)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def append_event(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> str:
    previous = conn.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = str(previous[0]) if previous else GENESIS_HASH
    event_id = uuid.uuid4().hex
    occurred_at = datetime.now(UTC).isoformat()
    payload_json = _canonical(payload)
    event_hash = _event_hash(
        event_id=event_id,
        occurred_at=occurred_at,
        kind=kind,
        payload_json=payload_json,
        prev_hash=prev_hash,
    )
    conn.execute(
        "INSERT INTO events(event_id, occurred_at, kind, payload_json, prev_hash, event_hash) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (event_id, occurred_at, kind, payload_json, prev_hash, event_hash),
    )
    return event_id


def verify_chain(database: Path) -> tuple[bool, str, int]:
    if not database.is_file():
        return False, "STATE STORE MISSING", 0
    with read_connection(database) as conn:
        rows = conn.execute("SELECT * FROM events ORDER BY seq").fetchall()
    previous = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != previous:
            return False, f"LEDGER LINK BROKEN at sequence {row['seq']}", len(rows)
        expected = _event_hash(
            event_id=row["event_id"],
            occurred_at=row["occurred_at"],
            kind=row["kind"],
            payload_json=row["payload_json"],
            prev_hash=row["prev_hash"],
        )
        if row["event_hash"] != expected:
            return False, f"LEDGER HASH BROKEN at sequence {row['seq']}", len(rows)
        previous = row["event_hash"]
    return True, "LEDGER VERIFIED", len(rows)
