from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from divineos.store import append_event, connect, transaction, verify_chain


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(database: Path, destination: Path) -> Path:
    """Create and verify a SQLite-consistent backup at a new path."""
    target = destination.expanduser().absolute()
    if target.exists():
        raise FileExistsError(f"backup destination already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_conn = connect(database)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    ok, message, event_count = verify_chain(target)
    if not ok:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"backup verification failed: {message}")
    checksum = _sha256(target)
    manifest = {
        "backup": target.name,
        "created_at": datetime.now(UTC).isoformat(),
        "event_count": event_count,
        "sha256": checksum,
        "verification": message,
    }
    manifest_path = target.with_suffix(target.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with transaction(database) as conn:
        append_event(
            conn,
            "backup.created",
            {"backup": target.name, "event_count": event_count, "sha256": checksum},
        )
    return manifest_path


def verify_backup(backup: Path) -> tuple[bool, str]:
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
    ok, message, count = verify_chain(target)
    if not ok:
        return False, message
    if manifest.get("event_count") != count:
        return False, "BACKUP EVENT COUNT MISMATCH"
    return True, f"BACKUP VERIFIED ({count} events)"


def restore_backup(backup: Path, destination_home: Path) -> Path:
    """Restore only into a home that does not already contain state."""
    ok, message = verify_backup(backup)
    if not ok:
        raise RuntimeError(message)
    home = destination_home.expanduser().absolute()
    restored = home / "state.db"
    if restored.exists():
        raise FileExistsError(f"restore destination already has state: {restored}")
    home.mkdir(parents=True, exist_ok=True)
    source_conn = sqlite3.connect(backup)
    target_conn = sqlite3.connect(restored)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()
    verified, chain_message, _ = verify_chain(restored)
    if not verified:
        restored.unlink(missing_ok=True)
        raise RuntimeError(f"restored chain verification failed: {chain_message}")
    with transaction(restored) as conn:
        append_event(
            conn,
            "backup.restored",
            {"backup": backup.name, "verification": message},
        )
    return restored
