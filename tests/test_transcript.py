from __future__ import annotations

import base64
import json
import os
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import pytest

from divineos.lifecycle import dispatch
from divineos.backup import create_backup, restore_backup
from divineos.runtime import Runtime
from divineos.store import append_event, transaction
from divineos.transcript import MAX_PENDING_BYTES
from test_history import request
from test_lifecycle import invoke

pytest_plugins = ("test_lifecycle",)


def raw_bytes(runtime, session):
    return b"".join(
        base64.b64decode(row["payload"]["data_base64"])
        for row in runtime.history(session_id=session)
        if row["kind"] == "history.transcript"
    )


def test_transcript_bytes_are_retained_once_incrementally_without_format_assumptions(
    state, tmp_path
):
    path = tmp_path / "transcript.jsonl"
    original = b'{"role":"user","text":"  hello  "}\n' + "😌".encode() + b"\xff\x00"
    path.write_bytes(original)
    payload = request("Stop", last_assistant_message="final", transcript_path=str(path))
    assert invoke("Stop", request=payload)["continue"]
    assert raw_bytes(state, payload["session_id"]) == original
    assert invoke("Stop", request=payload)["continue"]
    assert raw_bytes(state, payload["session_id"]) == original
    with path.open("ab") as output:
        output.write(b"\nmore bytes\n")
    assert invoke("Stop", request=payload)["continue"]
    expected = original + b"\nmore bytes\n"
    assert raw_bytes(state, payload["session_id"]) == expected
    # No dependency on the continuing existence of the transcript.
    path.unlink()
    assert raw_bytes(state, payload["session_id"]) == expected
    assert state.health().healthy


@pytest.mark.parametrize("replacement", [b"short", b"changed bytes!!"])
def test_shrink_or_rewrite_refuses_and_preserves_existing_history(state, tmp_path, replacement):
    path = tmp_path / "transcript"
    path.write_bytes(b"original bytes")
    payload = request(
        "PreToolUse", tool_name="Bash", tool_use_id="id", tool_input={}, transcript_path=str(path)
    )
    assert dispatch(payload).get("continue", True)
    before = state.history()
    path.write_bytes(replacement)
    output = dispatch(payload)
    assert "TRANSCRIPT" in output["systemMessage"]
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert state.history() == before


def test_large_transcript_chunks_preserve_middle_and_backlog_is_not_clipped(state, tmp_path):
    path = tmp_path / "transcript"
    data = b"begin\n" + b"middle\n" * 25_000 + b"end\n"
    path.write_bytes(data)
    payload = request("Stop", last_assistant_message="reply", transcript_path=str(path))
    assert dispatch(payload)["continue"]
    assert raw_bytes(state, payload["session_id"]) == data
    before = state.history()
    with path.open("ab") as output:
        output.write(b"x" * (MAX_PENDING_BYTES + 1))
    result = dispatch(payload)
    assert not result["continue"]
    assert "nothing clipped" in result["stopReason"]
    assert state.history() == before


def test_missing_or_relative_transcript_path_is_loud(state, tmp_path):
    for path in ("relative.jsonl", str(tmp_path / "missing")):
        payload = request("Stop", last_assistant_message="reply", transcript_path=path)
        before = state.history()
        assert not dispatch(payload)["continue"]
        assert state.history() == before


def test_invalid_chunk_blocks_read_even_when_event_chain_is_valid(state, tmp_path):
    path = tmp_path / "transcript"
    path.write_bytes(b"original")
    payload = request("Stop", last_assistant_message="reply", transcript_path=str(path))
    assert dispatch(payload)["continue"]
    last = next(r for r in state.history() if r["kind"] == "history.transcript")
    chunk = {**last["payload"], "start": 2, "end": 10}
    with transaction(state.provenance.database) as conn:
        append_event(conn, "history.transcript", json.loads(json.dumps(chunk)))
    assert "transcript chunk sequence has a gap" in state.briefing()


def test_two_sessions_do_not_share_transcript_cursor(state, tmp_path):
    path = tmp_path / "transcript"
    path.write_bytes(b"one source")
    for session in ("session-one", "session-two"):
        payload = {
            **request("Stop", last_assistant_message="reply", transcript_path=str(path)),
            "session_id": session,
        }
        assert dispatch(payload)["continue"]
        assert raw_bytes(state, session) == b"one source"


def test_concurrent_hook_processes_keep_bytes_once_and_each_observation(state, tmp_path):
    path = tmp_path / "transcript"
    path.write_bytes(b"concurrent recording\n" * 5_000)
    payload = request("Stop", last_assistant_message="reply", transcript_path=str(path))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(lambda _: invoke("Stop", request=payload), range(2)))
    assert all(output["continue"] for output in outputs)
    rows = state.history(session_id=payload["session_id"])
    assert sum(r["kind"] == "history.observed" for r in rows) == 2
    assert raw_bytes(state, payload["session_id"]) == path.read_bytes()


def test_failure_after_transcript_append_rolls_back_whole_recording(state, tmp_path, monkeypatch):
    import divineos.runtime as runtime_module

    path = tmp_path / "transcript"
    path.write_bytes(b"arriving bytes")
    payload = request("Stop", last_assistant_message="reply", transcript_path=str(path))
    before = state.history()

    def unavailable(*args, **kwargs):
        raise OSError("synthetic failure after transcript recording")

    monkeypatch.setattr(runtime_module, "append_event", unavailable)
    assert not dispatch(payload)["continue"]
    assert state.history() == before


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="host does not support named pipes")
def test_nonregular_transcript_is_refused_without_waiting_for_a_writer(state, tmp_path):
    path = tmp_path / "pipe"
    os.mkfifo(path)
    payload = request("Stop", last_assistant_message="reply", transcript_path=str(path))
    output = dispatch(payload)
    assert not output["continue"]
    assert "regular file" in output["stopReason"]


def test_verified_backup_restore_preserves_raw_history_after_source_is_gone(state, tmp_path):
    path = tmp_path / "transcript"
    path.write_bytes("A correction in the middle. 😌\n".encode())
    payload = request("Stop", last_assistant_message="A full reply", transcript_path=str(path))
    assert dispatch(payload)["continue"]
    original = state.history(session_id=payload["session_id"])
    backup = tmp_path / "backup.db"
    create_backup(state.provenance, backup)
    path.unlink()
    database = restore_backup(backup, tmp_path / "restoration-proof", occupant="Serein")
    restored = Runtime(replace(state.provenance, home=database.parent, database=database))
    assert restored.history(session_id=payload["session_id"]) == original
