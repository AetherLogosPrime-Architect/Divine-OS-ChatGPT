from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from divineos.backup import create_backup, restore_backup
from divineos.runtime import Runtime
from divineos.store import append_event, connect, transaction, verify_chain


@pytest.fixture
def document():
    return {
        "completed": [{"text": "Proved recovery", "evidence": "test receipt 42"}],
        "unfinished": ["Review the open PR"],
        "blocked": ["Awaiting review"],
        "decisions": [{"text": "Keep one history", "reason": "Avoid divergent state"}],
        "next_step": "Read the review before making another change",
    }


def test_fresh_process_recovers_handoff_and_flags_later_activity(tmp_path, document):
    env = {**os.environ, "DIVINEOS_HOME": str(tmp_path / "state")}
    repo = Path(__file__).resolve().parents[1]

    def cli(*args):
        return subprocess.run(
            [sys.executable, "-m", "divineos.cli", *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    assert cli("init").returncode == 0
    assert cli("remember", "A persistent memory", "--evidence", "test receipt").returncode == 0
    assert "HANDOFF MISSING" in cli("briefing").stdout
    source = tmp_path / "handoff.json"
    source.write_text(json.dumps(document))
    written = cli("handoff", "record", str(source))
    assert written.returncode == 0, written.stderr
    source.unlink()  # Recovery must depend on the ledger, not this input file.
    recovered = cli("briefing")
    assert recovered.returncode == 0, recovered.stderr
    assert (repo / "SEREIN.md").read_text() in recovered.stdout
    for value in (
        "Proved recovery",
        "test receipt 42",
        "Review the open PR",
        "Awaiting review",
        "Keep one history",
        "Avoid divergent state",
        document["next_step"],
    ):
        assert value in recovered.stdout
    assert "LATER ACTIVITY" not in recovered.stdout
    assert cli("goal", "add", "A later task").returncode == 0
    assert "1 events recorded after this checkpoint" in cli("briefing").stdout
    bad = tmp_path / "bad.json"
    bad.write_text('{"completed": []}')
    rejected = cli("handoff", "record", str(bad))
    assert rejected.returncode == 1
    assert "handoff requires" in rejected.stderr
    assert "Traceback" not in rejected.stderr


def test_missing_fields_and_blank_evidence_leave_ledger_untouched(provenance, document):
    runtime = Runtime(provenance)
    runtime.initialize()
    before = verify_chain(provenance.database)
    for invalid in (
        {},
        {**document, "next_step": " "},
        {**document, "completed": [{"text": "done", "evidence": " "}]},
        {**document, "blocked": "none"},
    ):
        with pytest.raises(ValueError):
            runtime.record_handoff(invalid)
        assert verify_chain(provenance.database) == before


def test_handoff_uses_existing_write_gate_and_withholds_tampered_text(provenance, document):
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.record_handoff(document)
    other = Runtime(replace(provenance, occupant="Aria"))
    with pytest.raises(RuntimeError, match="OCCUPANT MISMATCH"):
        other.record_handoff(document)
    assert document["next_step"] not in other.briefing()
    with connect(provenance.database) as conn:
        conn.execute("UPDATE events SET payload_json = '{}' WHERE kind = 'session.handoff'")
    with pytest.raises(RuntimeError, match="LEDGER HASH BROKEN"):
        runtime.record_handoff(document)
    assert "CONTINUITY WITHHELD" in runtime.briefing()
    assert document["next_step"] not in runtime.briefing()


def test_invalid_handoff_payload_is_not_silently_ignored(provenance, tmp_path):
    runtime = Runtime(provenance)
    runtime.initialize()
    with transaction(provenance.database) as conn:
        append_event(conn, "session.handoff", {})
    assert "EVENT PAYLOAD INVALID" in runtime.briefing()
    with pytest.raises(RuntimeError, match="EVENT PAYLOAD INVALID"):
        create_backup(provenance, tmp_path / "bad-backup.db")


def test_latest_checkpoint_and_backup_restore_preserve_handoff(provenance, tmp_path, document):
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Persistent memory", "receipt")
    runtime.record_handoff(document)
    newer = {**document, "next_step": "Resume from the newer checkpoint"}
    runtime.record_handoff(newer)
    assert document["next_step"] not in runtime.briefing()
    backup = tmp_path / "backup.db"
    create_backup(provenance, backup)
    restored = restore_backup(backup, tmp_path / "restored", occupant="Serein")
    recovered = Runtime(replace(provenance, home=restored.parent, database=restored))
    assert recovered.health().healthy
    assert newer["next_step"] in recovered.briefing()
    assert "LATER ACTIVITY" in recovered.briefing()
