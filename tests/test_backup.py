from __future__ import annotations

import json
from pathlib import Path

import pytest

from divineos.backup import create_backup, restore_backup, verify_backup
from divineos.paths import Provenance
from divineos.runtime import Runtime
from divineos.store import read_connection, verify_chain


def test_create_verify_and_restore_are_one_proven_route(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    runtime.remember("Backups are claims until restoration succeeds.", "architecture contract")
    backup = tmp_path / "backups" / "state.db"

    manifest = create_backup(provenance.database, backup)
    ok, message = verify_backup(backup)
    restored = restore_backup(backup, tmp_path / "independent-home")

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
    manifest_path = create_backup(provenance.database, backup)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert verify_backup(backup) == (False, "BACKUP CHECKSUM MISMATCH")


def test_restore_refuses_to_overwrite_existing_state(
    provenance: Provenance, tmp_path: Path
) -> None:
    runtime = Runtime(provenance)
    runtime.initialize()
    backup = tmp_path / "state.db"
    create_backup(provenance.database, backup)
    occupied_home = tmp_path / "occupied"
    occupied_home.mkdir()
    (occupied_home / "state.db").write_bytes(b"do not overwrite")

    with pytest.raises(FileExistsError, match="already has state"):
        restore_backup(backup, occupied_home)

    assert (occupied_home / "state.db").read_bytes() == b"do not overwrite"
