from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from divineos import cli, runtime as runtime_module
from divineos.paths import Provenance
from divineos.runtime import Runtime
from divineos.store import connect, verify_chain


def test_unknown_home_stays_untouched_until_explicit_init(
    provenance: Provenance,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "Runtime", lambda: Runtime(provenance))
    for command in (
        ["status"],
        ["briefing"],
        ["remember", "unearned memory", "--evidence", "none"],
        ["goal", "add", "unearned goal"],
        ["repair", "rebuild-projections"],
        ["backup", "create", str(tmp_path / "unearned.db")],
    ):
        assert cli.main(command) == 1
        output = capsys.readouterr()
        assert "STATE STORE MISSING" in output.out + output.err
        assert not provenance.home.exists()

    assert cli.main(["init"]) == 0
    assert provenance.database.is_file()
    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 1)


def test_existing_uninitialized_file_is_not_rewritten_by_init(
    provenance: Provenance, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    provenance.home.mkdir()
    provenance.database.write_bytes(b"")
    monkeypatch.setattr(cli, "Runtime", lambda: Runtime(provenance))

    assert cli.main(["status"]) == 1
    assert "STATE UNINITIALIZED" in capsys.readouterr().out
    assert cli.main(["init"]) == 1
    assert "INIT REFUSED: STATE UNINITIALIZED" in capsys.readouterr().err
    assert provenance.database.read_bytes() == b""


def test_backup_restoration_is_available_when_current_home_is_missing(
    provenance: Provenance,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    owner = Runtime(provenance)
    owner.initialize()
    owner.remember("recovered", "firsthand receipt")
    backup = tmp_path / "backup.db"
    from divineos.backup import create_backup

    create_backup(provenance, backup)
    missing_home = tmp_path / "missing-home"
    replacement = Provenance(
        repo=provenance.repo,
        home=missing_home,
        database=missing_home / "state.db",
        interpreter=provenance.interpreter,
        occupant=provenance.occupant,
    )
    monkeypatch.setattr(cli, "Runtime", lambda: Runtime(replacement))

    assert cli.main(["backup", "verify", str(backup)]) == 0
    assert "BACKUP VERIFIED" in capsys.readouterr().out
    restored_home = tmp_path / "restored-home"
    assert cli.main(["backup", "restore", str(backup), "--to-home", str(restored_home)]) == 0
    assert "Backup restored and verified" in capsys.readouterr().out
    assert not missing_home.exists()
    with sqlite3.connect(restored_home / "state.db") as conn:
        assert conn.execute("SELECT text FROM memories").fetchone()[0] == "recovered"


def test_briefing_reads_one_verified_snapshot_during_concurrent_drift(
    provenance: Provenance, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("verified snapshot", "firsthand receipt")
    original_verify = runtime_module.verify_projections_on

    def drift_after_ledger_read(conn: sqlite3.Connection) -> tuple[bool, str]:
        with connect(provenance.database) as writer:
            writer.execute("UPDATE memories SET text = 'later drift'")
            writer.commit()
        return original_verify(conn)

    monkeypatch.setattr(runtime_module, "verify_projections_on", drift_after_ledger_read)
    briefing, health = runtime.briefing_result()

    assert health.healthy
    assert "verified snapshot" in briefing
    assert "later drift" not in briefing
    monkeypatch.setattr(runtime_module, "verify_projections_on", original_verify)
    assert "PROJECTION DRIFT" in runtime.briefing()


def test_briefing_loads_identity_and_refuses_unreadable_identity(provenance: Provenance) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("private continuity", "receipt")
    identity = provenance.repo / "SEREIN.md"
    identity.write_text("I take responsibility for my corrections.\n", encoding="utf-8")
    briefing, health = Runtime(provenance).briefing_result()
    assert health.healthy
    assert identity.read_text() in briefing
    assert str(identity) in briefing
    assert "outside ledger" in briefing

    for invalid in (b"", b"\xff"):
        identity.write_bytes(invalid)
        briefing, health = Runtime(provenance).briefing_result()
        assert not health.healthy
        assert "IDENTITY UNREADABLE" in briefing
        assert "CONTINUITY WITHHELD" in briefing
        assert "private continuity" not in briefing
