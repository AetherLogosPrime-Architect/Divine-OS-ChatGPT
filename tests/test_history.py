from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from divineos import cli
from divineos.lifecycle import dispatch
from divineos.runtime import Runtime
from divineos.store import connect, transaction, append_event
from test_lifecycle import REPO, invoke

pytest_plugins = ("test_lifecycle",)


def request(event, **fields):
    return {
        "hook_event_name": event,
        "cwd": str(REPO),
        "session_id": "synthetic-history",
        "turn_id": "turn-1",
        **fields,
    }


def test_real_configured_routes_record_prompts_tools_results_and_reply(state):
    prompt = request("UserPromptSubmit", prompt="  correction 😌\nKeep every word.  ")
    call = request(
        "PreToolUse",
        tool_name="Bash",
        tool_use_id="call-1",
        tool_input={"command": "example", "nested": [None, True, 42]},
    )
    result = request(
        "PostToolUse",
        tool_name="Bash",
        tool_use_id="call-1",
        tool_input=call["tool_input"],
        tool_response={"output": "full\nresult 😌"},
    )
    reply = request("Stop", stop_hook_active=False, last_assistant_message="Full reply.\n😌")
    for payload in (prompt, call, result, reply):
        assert invoke(payload["hook_event_name"], request=payload).get("continue", True) is True
    records = state.history(session_id="synthetic-history")
    assert [r["payload"]["request"] for r in records] == [prompt, call, result, reply]
    # Observations do not become curated memories by being recorded.
    assert "Keep every word" not in state.briefing()
    assert "Full reply" not in state.briefing()


def test_identical_arrivals_and_retries_remain_distinct(state):
    payload = request("UserPromptSubmit", prompt="yes")
    for _ in range(3):
        assert dispatch(payload)["continue"] is True
    rows = state.history(session_id=payload["session_id"])
    assert len(rows) == 3
    assert len({r["event_id"] for r in rows}) == 3
    assert all(r["payload"]["request"] == payload for r in rows)


@pytest.mark.parametrize(
    "event,fields",
    [
        ("PreToolUse", {"tool_name": "Bash", "tool_use_id": "id", "tool_input": {}}),
        (
            "PostToolUse",
            {"tool_name": "Bash", "tool_use_id": "id", "tool_input": {}, "tool_response": None},
        ),
        ("Stop", {"last_assistant_message": None}),
        ("PreCompact", {"trigger": "auto"}),
        ("PostCompact", {"trigger": "auto"}),
        ("SessionEnd", {"reason": "other"}),
    ],
)
def test_each_added_boundary_is_routed_and_recorded(state, event, fields):
    payload = request(event, **fields)
    assert invoke(event, request=payload).get("continue", True) is True
    assert state.history()[-1]["payload"]["request"] == payload


def test_recording_failure_refuses_continuation_before_delivery(state, monkeypatch):
    def unavailable(*args):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(Runtime, "record_observation", unavailable)
    for event, fields in [
        ("UserPromptSubmit", {"prompt": "record me"}),
        ("PreToolUse", {"tool_name": "Bash", "tool_use_id": "id", "tool_input": {}}),
        (
            "PostToolUse",
            {
                "tool_name": "Bash",
                "tool_use_id": "id",
                "tool_input": {},
                "tool_response": "already ran",
            },
        ),
        ("Stop", {"last_assistant_message": "record me too"}),
    ]:
        output = dispatch(request(event, **fields))
        assert output.get("continue", False) is False
        assert "synthetic disk failure" in output["systemMessage"]
        if event == "PreToolUse":
            assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
            assert "continue" not in output
            assert "stopReason" not in output
        if event in {"UserPromptSubmit", "PostToolUse"}:
            assert output["decision"] == "block"


def test_recorded_arrival_survives_failed_delivery_and_retry(state):
    state.remember("x" * 25_000, "oversized synthetic orientation")
    payload = request("UserPromptSubmit", prompt="do not lose this")
    assert dispatch(payload)["continue"] is False
    rows = state.history(session_id=payload["session_id"])
    assert rows[0]["payload"]["request"]["prompt"] == payload["prompt"]


def test_history_export_is_verified_and_can_filter_sessions(state, capsys):
    payload = request("Stop", last_assistant_message="saved")
    assert dispatch(payload)["continue"]
    assert cli.main(["history", "--session", payload["session_id"]]) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 1
    assert rows[0]["payload"]["request"] == payload
    assert cli.main(["history", "--after", str(rows[0]["seq"])]) == 0
    assert capsys.readouterr().out == ""
    with connect(state.provenance.database) as conn:
        conn.execute("UPDATE events SET payload_json = '{}' WHERE kind = 'history.observed'")
    assert cli.main(["history"]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "LEDGER HASH BROKEN" in captured.err


def test_malformed_observation_is_not_accepted_as_healthy_history(state):
    with transaction(state.provenance.database) as conn:
        append_event(conn, "history.observed", {"source": "codex-hook", "request": {}})
    assert "EVENT PAYLOAD INVALID" in state.briefing()
    with pytest.raises(RuntimeError):
        state.history()


def test_interruption_is_recorded_without_claiming_it_can_be_prevented(state, monkeypatch):
    payload = request("Interrupt")
    assert invoke("Interrupt", request=payload) == {}
    assert state.history()[-1]["payload"]["request"] == payload

    def unavailable(*args):
        raise OSError("synthetic interruption recording failure")

    monkeypatch.setattr(Runtime, "record_observation", unavailable)
    output = dispatch(payload)
    assert set(output) == {"systemMessage"}
    assert "recording failure" in output["systemMessage"]


@pytest.mark.parametrize("raw", ['{"prompt":"one","prompt":"two"}', '{"x":NaN}', "invalid"])
def test_invalid_wire_input_is_loud_and_uses_error_transport(state, raw):
    before = state.history()
    output = subprocess.run(
        [sys.executable, "-m", "divineos.lifecycle"],
        cwd=REPO,
        env=os.environ.copy(),
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )
    assert output.returncode == 2
    assert "invalid input" in output.stderr
    assert not output.stdout
    assert state.history() == before


def test_recording_route_honors_selected_witness_before_appending(state, tmp_path, monkeypatch):
    witness = tmp_path / "witness.json"
    state.retain_witness(witness)
    monkeypatch.setenv("DIVINEOS_WITNESS", str(witness))
    witness.unlink()
    before = state.history()
    output = dispatch(request("UserPromptSubmit", prompt="cannot append past missing witness"))
    assert output["decision"] == "block"
    assert "WITNESS UNAVAILABLE" in output["systemMessage"]
    assert state.history() == before
