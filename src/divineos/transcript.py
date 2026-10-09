"""Retain raw transcript bytes; no dependency on the host's private format."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path

from divineos.store import append_event

CHUNK_BYTES = 64 * 1024
MAX_PENDING_BYTES = 8 * 1024 * 1024


def validate_chunk(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != {
        "session_id",
        "path",
        "start",
        "end",
        "data_base64",
        "prefix_sha256",
    }:
        raise ValueError("transcript chunk has invalid fields")
    for key in ("session_id", "path", "data_base64", "prefix_sha256"):
        if not isinstance(payload[key], str) or not payload[key]:
            raise ValueError(f"transcript chunk has invalid {key}")
    if not Path(payload["path"]).is_absolute():
        raise ValueError("transcript chunk path must be absolute")
    for key in ("start", "end"):
        if type(payload[key]) is not int or payload[key] < 0:
            raise ValueError("transcript chunk offset is invalid")
    data = base64.b64decode(payload["data_base64"], validate=True)
    if not data or len(data) > CHUNK_BYTES or payload["end"] - payload["start"] != len(data):
        raise ValueError("transcript chunk length is invalid")
    return payload


def retain_transcript_on(conn: sqlite3.Connection, session_id: str, path: Path) -> None:
    if not path.is_absolute():
        raise ValueError("transcript path must be absolute")
    path = path.resolve()
    offset = 0
    expected_prefix = hashlib.sha256().hexdigest()
    for row in conn.execute(
        "SELECT payload_json FROM events WHERE kind = 'history.transcript' ORDER BY seq DESC"
    ):
        payload = json.loads(row[0])
        if payload["session_id"] == session_id and payload["path"] == str(path):
            offset = payload["end"]
            expected_prefix = payload["prefix_sha256"]
            break
    # Nonblocking open lets us reject pipes before a regular-file check, rather
    # than hanging until the host timeout and possibly losing the observation.
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb") as source:
        # fstat checks the opened descriptor, including paths replaced after open.
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("transcript must be a regular file")
        size = info.st_size
        if size < offset:
            raise RuntimeError("TRANSCRIPT SHRANK: previously recorded ending is missing")
        if size - offset > MAX_PENDING_BYTES:
            raise RuntimeError("TRANSCRIPT BACKLOG exceeds recording limit; nothing clipped")
        digest = hashlib.sha256()
        remaining = offset
        while remaining:
            chunk = source.read(min(CHUNK_BYTES, remaining))
            if not chunk:
                raise RuntimeError("TRANSCRIPT SHRANK while checking recorded prefix")
            digest.update(chunk)
            remaining -= len(chunk)
        if digest.hexdigest() != expected_prefix:
            raise RuntimeError("TRANSCRIPT PREFIX CHANGED: recorded bytes were rewritten")
        while offset < size:
            chunk = source.read(min(CHUNK_BYTES, size - offset))
            if not chunk:
                raise RuntimeError("TRANSCRIPT SHRANK while retaining new bytes")
            digest.update(chunk)
            payload = {
                "session_id": session_id,
                "path": str(path),
                "start": offset,
                "end": offset + len(chunk),
                "data_base64": base64.b64encode(chunk).decode("ascii"),
                "prefix_sha256": digest.hexdigest(),
            }
            append_event(conn, "history.transcript", payload)
            offset += len(chunk)
