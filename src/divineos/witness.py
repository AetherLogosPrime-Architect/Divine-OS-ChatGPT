"""Immutable receipts retained outside the state home; never auto-repaired."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def validate_location(path: Path, home: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("WITNESS PATH must be absolute")
    resolved = path.resolve()
    if resolved.is_relative_to(home.resolve()):
        raise ValueError("WITNESS PATH must be outside the state home")
    return resolved


def verify_witness_on(conn: sqlite3.Connection, path: Path, occupant: str) -> tuple[bool, str]:
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or set(receipt) != {
            "version",
            "occupant",
            "genesis_hash",
            "seq",
            "event_hash",
        }:
            raise ValueError("invalid receipt fields")
        if type(receipt["version"]) is not int or receipt["version"] != 1:
            raise ValueError("unknown receipt version")
        if type(receipt["seq"]) is not int or receipt["seq"] < 1:
            raise ValueError("invalid sequence")
        for field in ("genesis_hash", "event_hash"):
            value = receipt[field]
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError("invalid hash")
            int(value, 16)
    except (OSError, UnicodeError, ValueError) as exc:
        return False, f"WITNESS UNAVAILABLE: {path}: {exc}"
    if receipt["occupant"] != occupant:
        return False, "WITNESS OCCUPANT MISMATCH"
    genesis = conn.execute("SELECT event_hash FROM events ORDER BY seq LIMIT 1").fetchone()
    if genesis is None or genesis[0] != receipt["genesis_hash"]:
        return False, "WITNESS HISTORY MISMATCH: genesis differs"
    row = conn.execute("SELECT event_hash FROM events WHERE seq = ?", (receipt["seq"],)).fetchone()
    if row is None:
        return False, f"WITNESS HISTORY LOSS: retained sequence {receipt['seq']} is missing"
    if row[0] != receipt["event_hash"]:
        return False, f"WITNESS HISTORY MISMATCH at sequence {receipt['seq']}"
    return True, f"WITNESS VERIFIED through sequence {receipt['seq']}"


def create_witness_on(conn: sqlite3.Connection, path: Path, occupant: str) -> None:
    """Caller must verify the same database snapshot first."""
    first = conn.execute("SELECT event_hash FROM events ORDER BY seq LIMIT 1").fetchone()
    last = conn.execute("SELECT seq, event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    if first is None or last is None:
        raise RuntimeError("WITNESS REFUSED: history is empty")
    receipt = {
        "version": 1,
        "occupant": occupant,
        "genesis_hash": first[0],
        "seq": last[0],
        "event_hash": last[1],
    }
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
