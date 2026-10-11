from __future__ import annotations

from dataclasses import replace

import pytest

from divineos import cli
from divineos.paths import Provenance
from divineos.projections import rebuild_projections, verify_projections
from divineos.runtime import Runtime
from divineos.store import connect, verify_chain


def test_tampered_ledger_blocks_writes_and_withholds_continuity(
    provenance: Provenance,
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("private memory", "firsthand receipt")
    goal_id = runtime.add_goal("private goal")
    with connect(provenance.database) as conn:
        conn.execute("UPDATE events SET payload_json = '{}' WHERE seq = 2")
        conn.commit()

    for mutation in (
        lambda: runtime.remember("another memory", "receipt"),
        lambda: runtime.add_goal("another goal"),
        lambda: runtime.complete_goal(goal_id),
    ):
        with pytest.raises(RuntimeError, match="WRITE BLOCKED: LEDGER HASH BROKEN"):
            mutation()

    assert verify_chain(provenance.database) == (False, "LEDGER HASH BROKEN at sequence 2", 3)
    briefing = runtime.briefing()
    assert "CONTINUITY WITHHELD" in briefing
    assert "private memory" not in briefing
    assert "private goal" not in briefing


def test_projection_drift_blocks_writes_until_verified_rebuild(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("the original memory", "firsthand receipt")
    with connect(provenance.database) as conn:
        conn.execute("UPDATE memories SET text = 'quietly replaced'")
        conn.commit()

    with pytest.raises(RuntimeError, match="WRITE BLOCKED: PROJECTION DRIFT"):
        runtime.add_goal("proceed despite drift")
    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 2)
    assert "quietly replaced" not in runtime.briefing()

    rebuild_projections(provenance.database, occupant="Serein")
    runtime.add_goal("proceed after repair")
    assert verify_projections(provenance.database) == (True, "PROJECTIONS VERIFIED")
    assert "the original memory" in runtime.briefing()
    assert "proceed after repair" in runtime.briefing()


def test_another_occupant_cannot_read_write_or_repair_state(provenance: Provenance) -> None:
    owner = Runtime(provenance)
    owner.initialize()
    owner.remember("Serein only", "firsthand receipt")
    other = Runtime(replace(provenance, occupant="Aria"))

    assert "OCCUPANT MISMATCH" in other.briefing()
    assert "Serein only" not in other.briefing()
    with pytest.raises(RuntimeError, match="WRITE BLOCKED: OCCUPANT MISMATCH"):
        other.remember("wrong occupant", "receipt")
    with pytest.raises(RuntimeError, match="cannot rebuild another occupant's state"):
        rebuild_projections(provenance.database, occupant="Aria")
    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 2)


def test_missing_identity_blocks_writes_and_withholds_memories(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Serein only", "firsthand receipt")
    (provenance.repo / "SEREIN.md").unlink()

    with pytest.raises(RuntimeError, match="WRITE BLOCKED: IDENTITY MISSING"):
        runtime.add_goal("proceed without identity")
    assert "Serein only" not in runtime.briefing()
    assert "CONTINUITY WITHHELD" in runtime.briefing()


def test_cli_status_and_briefing_exit_unhealthy_on_projection_drift(
    provenance: Provenance, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Runtime", lambda: Runtime(provenance))
    assert cli.main(["init"]) == 0
    Runtime(provenance).remember("visible only if verified", "firsthand receipt")
    with connect(provenance.database) as conn:
        conn.execute("UPDATE memories SET active = 0")
        conn.commit()

    assert cli.main(["status"]) == 1
    assert "PROJECTION DRIFT" in capsys.readouterr().out
    assert cli.main(["briefing"]) == 1
    output = capsys.readouterr().out
    assert "CONTINUITY WITHHELD" in output
    assert "visible only if verified" not in output
