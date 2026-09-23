from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from divineos.paths import Provenance
from divineos.projections import verify_projections_on
from divineos.store import (
    append_event,
    transaction,
    verify_chain_on,
    verify_occupant,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_state(database: Path, occupant: str) -> tuple[bool, str, int]:
    if not database.is_file():
        return False, "STATE STORE MISSING", 0
    with closing(_open_readonly(database)) as conn:
        conn.execute("BEGIN")
        return _verify_state_on(conn, occupant)


def _open_readonly(database: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _verify_state_on(conn: sqlite3.Connection, occupant: str) -> tuple[bool, str, int]:
    ok, message, count = verify_chain_on(conn)
    if not ok:
        return False, message, count
    bound, message = verify_occupant(conn, occupant)
    if not bound:
        return False, message, count
    projections_ok, message = verify_projections_on(conn)
    if not projections_ok:
        return False, message, count
    return True, "CONTINUITY VERIFIED", count


def _prove_restoration(backup: Path, occupant: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="divineos-backup-verify-") as directory:
        restored = Path(directory) / "state.db"
        source = _open_readonly(backup)
        destination = sqlite3.connect(restored)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        ok, message, _ = _verify_state(restored, occupant)
        return ok, message


def create_backup(provenance: Provenance, destination: Path) -> Path:
    """Create and verify a SQLite-consistent backup at a new path."""
    database = provenance.database
    target = destination.expanduser().absolute()
    if target.exists():
        raise FileExistsError(f"backup destination already exists: {target}")
    identity = provenance.repo / "SEREIN.md"
    if not identity.is_file():
        raise RuntimeError(f"backup blocked: IDENTITY MISSING: {identity}")
    ok, message, _ = _verify_state(database, provenance.occupant)
    if not ok:
        raise RuntimeError(f"backup blocked: {message}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = _open_readonly(database)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    ok, message, event_count = _verify_state(target, provenance.occupant)
    if not ok:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"backup verification failed: {message}")
    restored_ok, restored_message = _prove_restoration(target, provenance.occupant)
    if not restored_ok:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"backup restoration failed: {restored_message}")
    checksum = _sha256(target)
    manifest = {
        "backup": target.name,
        "created_at": datetime.now(UTC).isoformat(),
        "event_count": event_count,
        "occupant": provenance.occupant,
        "sha256": checksum,
        "verification": message,
    }
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        with transaction(database) as conn:
            ok, message, _ = _verify_state_on(conn, provenance.occupant)
            if not ok:
                raise RuntimeError(f"backup blocked: source changed: {message}")
            append_event(
                conn,
                "backup.created",
                {"backup": target.name, "event_count": event_count, "sha256": checksum},
            )
    except Exception:
        manifest_path.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        raise
    return manifest_path


def verify_backup(backup: Path, *, occupant: str) -> tuple[bool, str]:
    target = backup.expanduser().absolute()
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    if not target.is_file():
        return False, f"BACKUP MISSING: {target}"
    if not manifest_path.is_file():
        return False, f"BACKUP MANIFEST MISSING: {manifest_path}"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"BACKUP MANIFEST UNREADABLE: {exc}"
    actual = _sha256(target)
    if manifest.get("sha256") != actual:
        return False, "BACKUP CHECKSUM MISMATCH"
    if manifest.get("occupant", occupant) != occupant:
        return False, "BACKUP OCCUPANT MISMATCH"
    ok, message, count = _verify_state(target, occupant)
    if not ok:
        return False, message
    if manifest.get("event_count") != count:
        return False, "BACKUP EVENT COUNT MISMATCH"
    restored_ok, restored_message = _prove_restoration(target, occupant)
    if not restored_ok:
        return False, f"BACKUP RESTORATION FAILED: {restored_message}"
    return True, f"BACKUP VERIFIED ({count} events)"


def restore_backup(backup: Path, destination_home: Path, *, occupant: str) -> Path:
    """Restore only into a home that does not already contain state."""
    ok, message = verify_backup(backup, occupant=occupant)
    if not ok:
        raise RuntimeError(message)
    home = destination_home.expanduser().absolute()
    restored = home / "state.db"
    if restored.exists():
        raise FileExistsError(f"restore destination already has state: {restored}")
    home.mkdir(parents=True, exist_ok=True)
    source_conn = _open_readonly(backup)
    target_conn = sqlite3.connect(restored)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    verified, state_message, _ = _verify_state(restored, occupant)
    if not verified:
        restored.unlink(missing_ok=True)
        raise RuntimeError(f"restored state verification failed: {state_message}")
    try:
        with transaction(restored) as conn:
            verified, state_message, _ = _verify_state_on(conn, occupant)
            if not verified:
                raise RuntimeError(f"restored state changed: {state_message}")
            append_event(
                conn,
                "backup.restored",
                {"backup": backup.name, "verification": message},
            )
    except Exception:
        restored.unlink(missing_ok=True)
        raise
    return restored
