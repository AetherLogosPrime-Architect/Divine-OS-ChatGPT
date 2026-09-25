from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from divineos import backup as backup_module
from divineos.backup import create_backup, restore_backup, verify_backup
from divineos.paths import Provenance
from divineos.runtime import Runtime
from divineos.store import connect, read_connection, verify_chain


def test_create_verify_and_restore_are_one_proven_route(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Backups are claims until restoration succeeds.", "architecture contract")
    backup = tmp_path / "backups" / "state.db"

    manifest = create_backup(provenance, backup)
    ok, message = verify_backup(backup, occupant=provenance.occupant)
    restored = restore_backup(backup, tmp_path / "independent-home", occupant=provenance.occupant)

    assert manifest.is_file()
    assert ok
    assert message == "BACKUP VERIFIED (2 events)"
    assert verify_chain(restored) == (True, "LEDGER VERIFIED", 3)
    with read_connection(restored) as conn:
        assert conn.execute("SELECT text FROM memories").fetchone()[0].startswith("Backups")


def test_checksum_tampering_is_loud(provenance: Provenance, tmp_path: Path) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    backup = tmp_path / "state.db"
    manifest_path = create_backup(provenance, backup)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert verify_backup(backup, occupant=provenance.occupant) == (
        False,
        "BACKUP CHECKSUM MISMATCH",
    )


def test_restore_refuses_to_overwrite_existing_state(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    backup = tmp_path / "state.db"
    create_backup(provenance, backup)
    occupied_home = tmp_path / "occupied"
    occupied_home.mkdir()
    (occupied_home / "state.db").write_bytes(b"do not overwrite")

    with pytest.raises(FileExistsError, match="already has state"):
        restore_backup(backup, occupied_home, occupant=provenance.occupant)

    assert (occupied_home / "state.db").read_bytes() == b"do not overwrite"


def test_backup_refuses_projection_drift_without_creating_a_receipt(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("memory from the ledger", "firsthand receipt")
    with connect(provenance.database) as conn:
        conn.execute("UPDATE memories SET text = 'silently changed'")
        conn.commit()

    target = tmp_path / "backups" / "state.db"
    with pytest.raises(RuntimeError, match="backup blocked: PROJECTION DRIFT"):
        create_backup(provenance, target)

    assert not target.exists()
    assert verify_chain(provenance.database) == (True, "LEDGER VERIFIED", 2)


def test_checksum_valid_backup_with_projection_drift_cannot_be_verified_or_restored(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("original", "firsthand receipt")
    target = tmp_path / "backup.db"
    manifest_path = create_backup(provenance, target)

    with sqlite3.connect(target) as conn:
        conn.execute("UPDATE memories SET text = 'drifted'")
        conn.commit()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert verify_backup(target, occupant="Serein") == (
        False,
        "PROJECTION DRIFT: memories/goals do not match the ledger",
    )
    destination = tmp_path / "restore-home"
    with pytest.raises(RuntimeError, match="PROJECTION DRIFT"):
        restore_backup(target, destination, occupant="Serein")
    assert not (destination / "state.db").exists()


def test_wrong_occupant_cannot_create_or_restore_a_backup(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Serein only", "firsthand receipt")
    wrong = replace(provenance, occupant="Aria")
    with pytest.raises(RuntimeError, match="OCCUPANT MISMATCH"):
        create_backup(wrong, tmp_path / "wrong.db")

    target = tmp_path / "valid.db"
    create_backup(provenance, target)
    assert verify_backup(target, occupant="Aria") == (False, "BACKUP OCCUPANT MISMATCH")
    with pytest.raises(RuntimeError, match="BACKUP OCCUPANT MISMATCH"):
        restore_backup(target, tmp_path / "other-home", occupant="Aria")


def test_interrupted_restore_removes_partial_state(
    provenance: Provenance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("recoverable", "firsthand receipt")
    backup = tmp_path / "backup.db"
    create_backup(provenance, backup)
    restored = tmp_path / "destination" / "state.db"
    original_copy = backup_module._copy_database

    def interrupt_copy(source: Path, destination: Path) -> None:
        if destination == restored:
            destination.write_bytes(b"partial state")
            raise sqlite3.OperationalError("simulated copy interruption")
        original_copy(source, destination)

    monkeypatch.setattr(backup_module, "_copy_database", interrupt_copy)
    with pytest.raises(sqlite3.OperationalError, match="simulated copy interruption"):
        restore_backup(backup, restored.parent, occupant="Serein")

    assert not restored.exists()
