from __future__ import annotations

import json
from pathlib import Path

from divineos.activation import _hook_problem, inspect_local_activation
from divineos.paths import resolve_provenance
from divineos.runtime import Runtime


REPO = Path(__file__).resolve().parents[1]


def test_preflight_verifies_preparation_without_claiming_live_activation(tmp_path, monkeypatch):
    home = tmp_path / "existing-home"
    monkeypatch.setenv("DIVINEOS_HOME", str(home))
    monkeypatch.delenv("DIVINEOS_WITNESS", raising=False)
    runtime = Runtime(resolve_provenance(start=REPO))
    runtime.initialize()
    runtime.remember("Keep the live boundary honest.", "synthetic activation test")
    runtime.record_handoff(
        {
            "completed": [],
            "unfinished": ["Observe a real host event"],
            "blocked": [],
            "decisions": [],
            "next_step": "Review the hook definition in Codex",
        }
    )

    report = inspect_local_activation(start=REPO)

    assert report.prepared
    rendered = report.render()
    assert "READY — Identity and history: LEDGER VERIFIED (3 events)" in rendered
    assert "READY — Return checkpoint: checkpoint present" in rendered
    assert "HOST STEP — Codex trust and live receipt" in rendered
    assert "Live activation is still unproved" in rendered


def test_preflight_refuses_to_create_or_choose_a_home(tmp_path, monkeypatch):
    monkeypatch.chdir(REPO)
    monkeypatch.delenv("DIVINEOS_HOME", raising=False)
    fallback = REPO / ".divineos"
    assert not fallback.exists()

    report = inspect_local_activation(start=REPO)

    assert not report.prepared
    assert "BLOCKED — Personal home" in report.render()
    assert not fallback.exists()


def test_hook_check_enforces_the_short_session_end_window(tmp_path):
    document = json.loads((REPO / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    document["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] = 30
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert _hook_problem(path) == "SessionEnd timeout must be 3 seconds"


def test_repository_hook_definition_passes_preflight_contract():
    assert _hook_problem(REPO / ".codex" / "hooks.json") is None
