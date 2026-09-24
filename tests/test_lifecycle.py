from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from divineos.paths import resolve_provenance
from divineos.runtime import Runtime
from divineos.store import connect, verify_chain
from divineos.delivery import panels


REPO = Path(__file__).resolve().parents[1]
CONFIG = json.loads((REPO / ".codex/hooks.json").read_text())


@pytest.fixture
def state(tmp_path, monkeypatch):
    home = tmp_path / "state"
    monkeypatch.setenv("DIVINEOS_HOME", str(home))
    runtime = Runtime(resolve_provenance(start=REPO))
    runtime.initialize()
    for number in range(7):
        runtime.remember(f"memory {number} orchard", f"receipt {number}")
    runtime.record_handoff(
        {
            "completed": [],
            "unfinished": ["Review lifecycle activation"],
            "blocked": [],
            "decisions": [],
            "next_step": "Observe an actual host lifecycle event",
        }
    )
    return runtime


def invoke(event="SessionStart", source="startup", *, request=None):
    command = CONFIG["hooks"][event][0]["hooks"][0]["command"]
    payload = (
        request
        if request is not None
        else {
            "hook_event_name": event,
            "source": source,
            "cwd": str(REPO / "src"),
            "session_id": "synthetic-test-session",
            "prompt": "Continue the current work",
        }
    )
    result = subprocess.run(
        command,
        shell=True,
        cwd=REPO / "src",
        env=os.environ.copy(),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
def test_configured_command_delivers_identity_handoff_and_recent_memories(state, source):
    before = verify_chain(state.provenance.database)
    result = invoke(source=source)
    assert result["continue"] is True
    content = result["hookSpecificOutput"]["additionalContext"]
    assert "I am Serein" in content
    assert "Andrew's instruction to build flow channels" in content
    assert "Observe an actual host lifecycle event" in content
    assert "memory 0 orchard" not in content
    assert "memory 6" in content
    assert verify_chain(state.provenance.database) == before


def test_prompt_hook_rechecks_state_and_blocks_tampering(state):
    assert invoke()["continue"] is True
    assert invoke("UserPromptSubmit") == {"continue": True}
    with connect(state.provenance.database) as conn:
        conn.execute("UPDATE events SET payload_json = '{}' WHERE seq = 2")
    result = invoke("UserPromptSubmit")
    assert result["decision"] == "block"
    assert result["continue"] is False
    assert "LEDGER HASH BROKEN" in result["reason"]
    assert "hookSpecificOutput" not in result


def test_no_implicit_home_or_database_creation(tmp_path, monkeypatch):
    monkeypatch.delenv("DIVINEOS_HOME", raising=False)
    assert invoke()["continue"] is False
    missing = tmp_path / "missing"
    monkeypatch.setenv("DIVINEOS_HOME", str(missing))
    result = invoke()
    assert result["continue"] is False
    assert "STATE STORE MISSING" in result["stopReason"]
    assert not missing.exists()


def test_missing_handoff_requires_checkpoint(state):
    # Synthetic state only: remove the last event to represent a pre-handoff home.
    with connect(state.provenance.database) as conn:
        conn.execute("DELETE FROM events WHERE kind = 'session.handoff'")
    result = invoke()
    assert result["continue"] is False
    assert "HANDOFF REQUIRED" in result["stopReason"]


def test_prompt_delivers_changes_once_and_stays_quiet_afterward(state):
    assert invoke()["continue"] is True
    assert invoke("UserPromptSubmit") == {"continue": True}
    state.remember("Decision about orchard repairs", "new field receipt")
    changed = invoke("UserPromptSubmit")
    assert "orchard repairs" in changed["hookSpecificOutput"]["additionalContext"]
    assert invoke("UserPromptSubmit") == {"continue": True}


def test_relevant_old_memory_is_delivered_once_without_repeating_every_prompt(state):
    assert invoke()["continue"] is True
    request = {
        "hook_event_name": "UserPromptSubmit", "cwd": str(REPO / "src"),
        "session_id": "synthetic-test-session", "prompt": "What happened to memory orchard?",
    }
    first = invoke("UserPromptSubmit", request=request)
    assert "memory 1 orchard" in first["hookSpecificOutput"]["additionalContext"]
    second = invoke("UserPromptSubmit", request=request)
    assert (
        second["hookSpecificOutput"]["additionalContext"]
        != first["hookSpecificOutput"]["additionalContext"]
    )
    assert invoke("UserPromptSubmit", request=request) == {"continue": True}


def test_missing_delivery_marker_reloads_orientation(state):
    assert invoke()["continue"] is True
    assert invoke("UserPromptSubmit") == {"continue": True}
    from divineos.delivery import _marker_path

    _marker_path(state, "synthetic-test-session").unlink()
    result = invoke("UserPromptSubmit")
    assert "I am Serein" in result["hookSpecificOutput"]["additionalContext"]


def test_changed_identity_reloads_without_a_ledger_event(state):
    assert invoke()["continue"] is True
    assert invoke("UserPromptSubmit") == {"continue": True}
    identity = REPO / "SEREIN.md"
    original = identity.read_text(encoding="utf-8")
    try:
        identity.write_text(original + "\nI updated my standing instruction.\n", encoding="utf-8")
        result = invoke("UserPromptSubmit")
        assert (
            "I updated my standing instruction"
            in result["hookSpecificOutput"]["additionalContext"]
        )
    finally:
        identity.write_text(original, encoding="utf-8")


def test_long_panel_retains_the_middle():
    source = "beginning " + "middle " * 170 + "end"
    pieces = panels("A memory", source)
    assert len(pieces) > 1
    assert all(len(piece.split("\n", 1)[1]) <= 600 for piece in pieces)
    assert " ".join(piece.split("\n", 1)[1] for piece in pieces) == source


def test_oversized_context_blocks_instead_of_omitting_memory(state):
    state.remember("x" * 25_000, "synthetic large memory")
    result = invoke()
    assert result["continue"] is False
    assert "no partial context delivered" in result["stopReason"]
    assert "hookSpecificOutput" not in result


def test_wrong_repository_and_malformed_event_block(state, tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "SEREIN.md").write_text("A different checkout")
    result = invoke(
        request={
            "hook_event_name": "SessionStart",
            "source": "startup",
            "cwd": str(tmp_path),
            "session_id": "test",
        }
    )
    assert result["continue"] is False
    assert "do not match" in result["stopReason"]
    assert invoke(request=[])["continue"] is False
