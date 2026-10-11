from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from divineos import cli
from divineos.backup import create_backup
from divineos.projections import rebuild_projections
from divineos.paths import Provenance
from divineos.runtime import Runtime
from divineos.store import connect, verify_chain


def test_retained_ending_detects_loss_despite_valid_chain_and_projections(provenance):
    runtime = Runtime(provenance)
    runtime.initialize()
    memory_id = runtime.remember("retained memory", "synthetic test")
    goal = runtime.add_goal("finish foundation")
    witness = provenance.home.parent / "witness.json"
    runtime.retain_witness(witness)
    checked = Runtime(replace(provenance, witness=witness))
    assert checked.health().healthy
    checked.add_goal("later work")
    assert checked.health().healthy
    # Remove the witnessed ending and its projections: local checks still pass.
    with connect(provenance.database) as conn:
        conn.execute("DELETE FROM events WHERE seq >= 3")
        conn.execute("DELETE FROM goals")
        conn.commit()
    assert verify_chain(provenance.database)[0]
    assert runtime.health().healthy
    assert "WITNESS HISTORY LOSS" in checked.briefing()
    assert "retained memory" not in checked.briefing()
    with pytest.raises(RuntimeError, match="WITNESS HISTORY LOSS"):
        checked.memory(memory_id)
    for mutation in (
        lambda: checked.remember("new", "test"),
        lambda: checked.add_goal("new"),
        lambda: checked.complete_goal(goal),
        lambda: checked.record_handoff(
            {
                "completed": [],
                "unfinished": [],
                "blocked": [],
                "decisions": [],
                "next_step": "Investigate the missing ending",
            }
        ),
    ):
        with pytest.raises(RuntimeError, match="WRITE BLOCKED: WITNESS HISTORY LOSS"):
            mutation()
    with pytest.raises(RuntimeError, match="WITNESS HISTORY LOSS"):
        create_backup(checked.provenance, witness.with_name("backup.db"))
    assert not witness.with_name("backup.db").exists()
    with pytest.raises(RuntimeError, match="WITNESS HISTORY LOSS"):
        rebuild_projections(provenance.database, occupant="Serein", witness=witness)
    with pytest.raises(RuntimeError, match="INIT REFUSED"):
        checked.initialize()
    with pytest.raises(RuntimeError, match="WITNESS REFUSED"):
        checked.retain_witness(witness.with_name("replacement.json"))


@pytest.mark.parametrize("contents", [None, "[]", "{}", "invalid", '{"version":1}'])
def test_missing_or_malformed_witness_blocks(provenance, contents):
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("private", "test")
    witness = provenance.home.parent / "witness.json"
    if contents is not None:
        witness.write_text(contents)
    checked = Runtime(replace(provenance, witness=witness))
    assert not checked.health().readable
    assert "WITNESS UNAVAILABLE" in checked.briefing()
    with pytest.raises(RuntimeError, match="WRITE BLOCKED"):
        checked.add_goal("new")


def test_receipt_cannot_be_replaced_or_kept_inside_home(provenance):
    runtime = Runtime(provenance)
    runtime.initialize()
    witness = provenance.home.parent / "witness.json"
    runtime.retain_witness(witness)
    original = witness.read_bytes()
    with pytest.raises(FileExistsError):
        runtime.retain_witness(witness)
    assert witness.read_bytes() == original
    for path in (provenance.home / "witness.json", witness.relative_to(witness.parent)):
        with pytest.raises(ValueError, match="WITNESS PATH"):
            runtime.retain_witness(path)


def test_other_history_with_same_occupant_is_rejected(provenance):
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("original", "test")
    witness = provenance.home.parent / "witness.json"
    runtime.retain_witness(witness)
    other_home = provenance.home.parent / "other"
    other = Runtime(replace(provenance, home=other_home, database=other_home / "state.db"))
    other.initialize()
    other.remember("other", "test")
    checked = Runtime(replace(other.provenance, witness=witness))
    assert "WITNESS HISTORY MISMATCH" in checked.briefing()
    receipt = json.loads(witness.read_text())
    receipt["occupant"] = "Aria"
    witness.write_text(json.dumps(receipt))
    assert "WITNESS OCCUPANT MISMATCH" in runtime_witness(runtime, witness).briefing()


def runtime_witness(runtime, witness):
    return Runtime(replace(runtime.provenance, witness=witness))


def test_cli_retains_receipt_and_configured_checks_use_it(provenance, monkeypatch, capsys):
    monkeypatch.chdir(provenance.repo)
    monkeypatch.setenv("DIVINEOS_HOME", str(provenance.home))
    monkeypatch.delenv("DIVINEOS_WITNESS", raising=False)
    assert cli.main(["init"]) == 0
    assert cli.main(["remember", "synthetic", "--evidence", "test"]) == 0
    witness = provenance.home.parent / "witness.json"
    assert cli.main(["witness", "retain", str(witness)]) == 0
    monkeypatch.setenv("DIVINEOS_WITNESS", str(witness))
    assert cli.main(["status"]) == 0
    witness.unlink()
    assert cli.main(["briefing"]) == 1
    assert "CONTINUITY WITHHELD" in capsys.readouterr().out


def test_missing_store_with_retained_witness_cannot_initialize(provenance: Provenance):
    checked = Runtime(replace(provenance, witness=provenance.home.parent / "receipt.json"))
    with pytest.raises(RuntimeError, match="INIT REFUSED"):
        checked.initialize()
    assert not provenance.home.exists()


def test_fresh_process_requires_retained_history(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["DIVINEOS_HOME"] = str(tmp_path / "synthetic-home")
    env.pop("DIVINEOS_WITNESS", None)

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "divineos.cli", *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    assert run("init").returncode == 0
    assert run("remember", "synthetic memory", "--evidence", "test").returncode == 0
    assert run("goal", "add", "witness this ending").returncode == 0
    witness = tmp_path / "witness.json"
    assert run("witness", "retain", str(witness)).returncode == 0
    env["DIVINEOS_WITNESS"] = str(witness)
    assert run("status").returncode == 0
    with connect(tmp_path / "synthetic-home" / "state.db") as conn:
        conn.execute("DELETE FROM events WHERE seq = 3")
        conn.execute("DELETE FROM goals")
        conn.commit()
    result = run("briefing")
    assert result.returncode == 1
    assert "WITNESS HISTORY LOSS" in result.stdout
    assert "synthetic memory" not in result.stdout
    assert run("goal", "add", "continue anyway").returncode == 1
    assert run("repair", "rebuild-projections").returncode == 1
