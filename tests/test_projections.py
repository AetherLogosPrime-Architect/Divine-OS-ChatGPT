from __future__ import annotations

from divineos.paths import Provenance
from divineos.projections import rebuild_projections, verify_projections
from divineos.runtime import Runtime
from divineos.store import connect, read_connection, verify_chain


def test_projection_drift_is_loud_and_rebuildable(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("The ledger is the receipt.", "architecture contract")
    goal_id = runtime.add_goal("Prove replay")
    runtime.complete_goal(goal_id)
    with connect(provenance.database) as conn:
        conn.execute("UPDATE memories SET text = 'quietly rewritten'")
        conn.execute("DELETE FROM goals")
        conn.commit()

    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 4)
    assert verify_projections(provenance.database) == (
        False,
        "PROJECTION DRIFT: memories/goals do not match the ledger",
    )
    assert "!!! PROJECTION DRIFT" in runtime.briefing()

    rebuild_projections(provenance.database, occupant=provenance.occupant)

    assert verify_projections(provenance.database) == (True, "PROJECTIONS VERIFIED")
    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 5)
    with read_connection(provenance.database) as conn:
        assert (
            conn.execute("SELECT text FROM memories").fetchone()[0] == "The ledger is the receipt."
        )
        assert conn.execute("SELECT status FROM goals").fetchone()[0] == "done"


def test_rebuild_refuses_an_invalid_ledger(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    with connect(provenance.database) as conn:
        conn.execute("UPDATE events SET payload_json = '{}' WHERE seq = 1")
        conn.commit()

    try:
        rebuild_projections(provenance.database, occupant=provenance.occupant)
    except RuntimeError as exc:
        assert "cannot rebuild from an invalid ledger" in str(exc)
    else:
        raise AssertionError("invalid ledger was used as a rebuild source")
