from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from divineos.paths import Provenance
from divineos.runtime import Runtime
from divineos.store import connect, verify_chain


def test_initialization_is_idempotent_and_verifiable(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.initialize()

    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 1)


def test_memory_survives_a_fresh_runtime_instance(provenance: Provenance) -> None:
    first = Runtime(provenance)
    first.initialize()
    first.remember("Scarcity narrows scope; it does not lower standards.", "Andrew's correction")

    second = Runtime(provenance)
    briefing = second.briefing()

    assert "Scarcity narrows scope" in briefing
    assert "Andrew's correction" in briefing
    assert "LEDGER VERIFIED (2 events)" in briefing


def test_memory_requires_evidence(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()

    try:
        runtime.remember("A claim", "")
    except ValueError as exc:
        assert str(exc) == "memory evidence cannot be empty"
    else:
        raise AssertionError("an evidence-free memory was accepted")

    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 1)


def test_goal_lifecycle_is_recorded(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    goal_id = runtime.add_goal("Prove the first continuity slice")
    assert "Prove the first continuity slice" in runtime.briefing()

    runtime.complete_goal(goal_id)

    assert "Prove the first continuity slice" not in runtime.briefing()
    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 3)


def test_empty_memory_shouts_in_briefing(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()

    briefing = runtime.briefing()

    assert "!!! MEMORY EMPTY" in briefing
    assert "!!! NO ACTIVE GOAL" in briefing


def test_tampering_breaks_verification_and_shouts(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Keep the receipt.", "test fixture")
    with connect(provenance.database) as conn:
        conn.execute("UPDATE events SET payload_json = '{}' WHERE seq = 2")
        conn.commit()

    ok, message, count = verify_chain(provenance.database)

    assert not ok
    assert message == "LEDGER HASH BROKEN at sequence 2"
    assert count == 2
    assert "!!! LEDGER HASH BROKEN at sequence 2" in runtime.briefing()


def test_backup_is_only_valid_after_independent_restore(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Restore tests are part of backup tests.", "architecture contract")
    restored = tmp_path / "restored" / "state.db"
    restored.parent.mkdir()
    shutil.copy2(provenance.database, restored)

    assert restored != provenance.database
    assert verify_chain(restored) == (True, "LEDGER VERIFIED", 2)
    with sqlite3.connect(restored) as conn:
        assert conn.execute("SELECT text FROM memories").fetchone()[0].startswith("Restore tests")
