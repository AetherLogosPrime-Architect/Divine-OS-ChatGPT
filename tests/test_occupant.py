"""Real-process, real-SQLite acceptance tests for the occupant adapter.

Set DIVINEOS_TEST_SOURCE to a source checkout. No upstream conftest or hooks
are loaded. A simulated inherited home is fingerprinted around use.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools/occupant.py"
SOURCE = os.environ.get("DIVINEOS_TEST_SOURCE")
requires_source = pytest.mark.skipif(not SOURCE, reason="Set DIVINEOS_TEST_SOURCE for real-OS integration")


def run(state, *args, env=None, source=None):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(TOOL), "--source", str(source or SOURCE),
         "--state", str(state), *args], capture_output=True, text=True,
        encoding="utf-8", env=env, timeout=30,
    )


def ok(result):
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout)


@requires_source
def test_restart_recovers_note_without_inherited_store_writes(tmp_path):
    inherited = tmp_path / "inherited"
    inherited.mkdir()
    db = inherited / "event_ledger.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE personal (value TEXT)")
        conn.execute("INSERT INTO personal VALUES ('inherited sentinel')")
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    env = dict(os.environ, DIVINEOS_HOME=str(inherited), DIVINEOS_DB=str(db),
               DIVINEOS_FAMILY_DB=str(db), CLAUDE_SESSION_ID="inherited-session")
    state = tmp_path / "new"
    boot = ok(run(state, "bootstrap", "--name", "ChatGPT", env=env))
    assert boot["core"]["my_identity"] == "ChatGPT"
    assert Path(boot["resolved"]["ledger"]).is_relative_to(state)
    saved = ok(run(state, "remember", "--text", "Restart lighthouse observation survives a new process.", env=env))
    recall = ok(run(state, "recall", "--query", "lighthouse", env=env))
    assert recall["matches"][0]["knowledge_id"] == saved["knowledge_id"]
    assert recall["matches"][0]["source"] == "SYNTHESIZED"
    assert ok(run(state, "verify", env=env))["chain"]["ok"]
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in inherited.iterdir()) == ["event_ledger.db"]


@requires_source
def test_two_occupants_do_not_share_memory(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    ok(run(a, "bootstrap", "--name", "OccupantA"))
    ok(run(b, "bootstrap", "--name", "OccupantB"))
    ok(run(a, "remember", "--text", "Private amber telescope observation belongs to occupant A."))
    assert ok(run(b, "recall", "--query", "telescope"))["matches"] == []
    assert ok(run(b, "briefing"))["core"]["my_identity"] == "OccupantB"


@requires_source
def test_refuses_to_take_over_existing_directory_or_identity(tmp_path):
    unowned = tmp_path / "unowned"
    unowned.mkdir()
    (unowned / "sentinel.txt").write_text("keep")
    assert run(unowned, "bootstrap", "--name", "ChatGPT").returncode == 1
    assert (unowned / "sentinel.txt").read_text() == "keep"
    state = tmp_path / "owned"
    ok(run(state, "bootstrap", "--name", "OccupantA"))
    assert run(state, "bootstrap", "--name", "OccupantB").returncode == 1
    assert ok(run(state, "briefing"))["core"]["my_identity"] == "OccupantA"


@requires_source
def test_repeated_bootstrap_preserves_notes(tmp_path):
    state = tmp_path / "owned"
    ok(run(state, "bootstrap", "--name", "ChatGPT"))
    note = ok(run(state, "remember", "--text", "Repeated bootstrap preserves the amber lantern note."))
    ok(run(state, "bootstrap", "--name", "ChatGPT"))
    assert ok(run(state, "recall", "--query", "lantern"))["matches"][0]["knowledge_id"] == note["knowledge_id"]
    assert ok(run(state, "verify"))["chain"]["total"] == 2


@requires_source
def test_native_briefing_can_surface_occupants_note(tmp_path):
    state = tmp_path / "native"
    ok(run(state, "bootstrap", "--name", "NewOccupant"))
    ok(run(state, "remember", "--text", "The turquoise compass is the fresh occupant briefing acceptance note."))
    result = ok(run(state, "native-briefing"))
    assert "turquoise compass" in result["text"]
    assert not result["reports_incomplete"]


@requires_source
def test_example_setup_retains_provenance_and_is_repeatable(tmp_path):
    state = tmp_path / "adopted"
    setup = TOOL.parents[1] / "profiles/chatgpt.json"
    ok(run(state, "bootstrap", "--name", "ChatGPT"))
    adopted = ok(run(state, "adopt-setup", "--setup", str(setup)))
    assert adopted["status"] == "applied"
    assert len(adopted["core"]) == 9
    assert len(adopted["receipt"]["knowledge_ids"]) == 4
    entries = ok(run(state, "recall", "--query", "handoff"))["matches"]
    entry = next(x for x in entries if "early-handoff" in x["content"])
    assert entry["source"] == "INHERITED"
    assert entry["maturity"] == "RAW"
    assert entry["source_entity"] == "DivineOS session-pipeline interruption account"
    assert entry["source_events"] == [adopted["receipt"]["event_id"]]
    repeated = ok(run(state, "adopt-setup", "--setup", str(setup)))
    assert repeated["status"] == "already_applied"
    assert repeated["receipt"] == adopted["receipt"]
    assert ok(run(state, "verify"))["chain"]["total"] == 2
    assert not ok(run(state, "native-briefing"))["reports_incomplete"]


@requires_source
@pytest.mark.parametrize("fault", ["wrong_owner", "missing_reference"])
def test_bad_setup_does_not_change_core_or_ledger(tmp_path, fault):
    state = tmp_path / "unchanged"
    config = json.loads((TOOL.parents[1] / "profiles/chatgpt.json").read_text(encoding="utf-8"))
    if fault == "wrong_owner":
        config["name"] = "AnotherOccupant"
    else:
        config["lessons"][-1]["references"] = []
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(config), encoding="utf-8")
    before = ok(run(state, "bootstrap", "--name", "ChatGPT"))["core"]
    result = run(state, "adopt-setup", "--setup", str(invalid))
    assert result.returncode == 1
    assert ok(run(state, "briefing"))["core"] == before
    assert ok(run(state, "verify"))["chain"]["total"] == 1


@pytest.mark.parametrize("action", ["write", "sqlite", "subprocess"])
def test_audit_guard_blocks_external_operations_in_real_process(tmp_path, action):
    root = tmp_path / "profile"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    code = '''
import importlib.util, pathlib, sys, sqlite3, subprocess
spec=importlib.util.spec_from_file_location("occupant",sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
violations=[]
sys.addaudithook(module.write_guard(pathlib.Path(sys.argv[2]),violations))
try:
 if sys.argv[4]=="write": pathlib.Path(sys.argv[3]).write_text("should not land")
 elif sys.argv[4]=="sqlite": sqlite3.connect(sys.argv[3])
 else: subprocess.run([sys.executable,"-c","pass"])
except module.BoundaryViolation:
 assert violations
 sys.exit(0)
sys.exit(9)
'''
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(TOOL), str(root), str(outside), action],
                          capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, proc.stderr
    assert not outside.exists()
