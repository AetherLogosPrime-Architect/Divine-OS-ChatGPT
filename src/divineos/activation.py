"""Read-only preparation checks for connecting Divine OS to a local Codex host."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from divineos.lifecycle import SUPPORTED_EVENTS
from divineos.paths import repo_root, resolve_provenance
from divineos.runtime import Runtime
from divineos.store import read_connection


HOOK_COMMAND = (
    '"$(git rev-parse --show-toplevel)/.venv/bin/python" -I -m divineos.lifecycle'
)
HOOK_TIMEOUTS = {event: 30 for event in SUPPORTED_EVENTS}
HOOK_TIMEOUTS.update({"Interrupt": 3, "SessionEnd": 3})


@dataclass(frozen=True)
class Check:
    state: str
    name: str
    detail: str


@dataclass(frozen=True)
class ActivationReport:
    checks: tuple[Check, ...]

    @property
    def prepared(self) -> bool:
        return not any(check.state == "BLOCKED" for check in self.checks)

    def render(self) -> str:
        lines = ["Serein local activation preflight", ""]
        lines.extend(f"{check.state} — {check.name}: {check.detail}" for check in self.checks)
        lines.extend(
            [
                "",
                (
                    "LOCAL PREPARATION READY. Live activation is still unproved until Codex "
                    "loads the hooks and ordinary activity reaches the ledger."
                    if self.prepared
                    else "LOCAL PREPARATION BLOCKED. No state was created, repaired, or selected."
                ),
            ]
        )
        return "\n".join(lines)


def _hook_problem(path: Path) -> str | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return f"cannot read {path}: {exc}"
    if not isinstance(document, dict) or set(document) != {"hooks"}:
        return "top level must contain only 'hooks'"
    routes = document["hooks"]
    if not isinstance(routes, dict) or set(routes) != SUPPORTED_EVENTS:
        return "configured lifecycle events do not exactly match the OS recorder"
    for event in sorted(SUPPORTED_EVENTS):
        groups = routes[event]
        if not isinstance(groups, list) or len(groups) != 1 or not isinstance(groups[0], dict):
            return f"{event} must have one routing group"
        group = groups[0]
        expected_group_fields = {"hooks", "matcher"} if event == "SessionStart" else {"hooks"}
        if set(group) != expected_group_fields:
            return f"{event} has unexpected routing fields"
        if event == "SessionStart" and group["matcher"] != "^(startup|resume|clear|compact)$":
            return "SessionStart does not cover the four supported entry paths"
        commands = group["hooks"]
        if (
            not isinstance(commands, list)
            or len(commands) != 1
            or not isinstance(commands[0], dict)
        ):
            return f"{event} must have one command"
        command = commands[0]
        expected_fields = {"type", "command", "timeout"}
        if event in {"SessionStart", "UserPromptSubmit"}:
            expected_fields.add("additionalContextLimit")
        if set(command) != expected_fields:
            return f"{event} command has unexpected fields"
        if command["type"] != "command" or command["command"] != HOOK_COMMAND:
            return f"{event} does not route to this checkout's OS entry point"
        if command["timeout"] != HOOK_TIMEOUTS[event]:
            return f"{event} timeout must be {HOOK_TIMEOUTS[event]} seconds"
        if event in {"SessionStart", "UserPromptSubmit"} and command["additionalContextLimit"] != 0:
            return f"{event} must leave context sizing to the OS"
    return None


def inspect_local_activation(*, start: Path | None = None) -> ActivationReport:
    """Inspect local prerequisites without mutating continuity or host trust."""
    repo = repo_root(start)
    checks: list[Check] = []

    configured = os.environ.get("DIVINEOS_HOME", "").strip()
    if not configured:
        checks.append(
            Check("BLOCKED", "Personal home", "DIVINEOS_HOME has not selected existing state")
        )
        return _finish_static_checks(repo, checks)
    configured_path = Path(configured).expanduser()
    if not configured_path.is_absolute():
        checks.append(
            Check("BLOCKED", "Personal home", "DIVINEOS_HOME must be an absolute path")
        )
        return _finish_static_checks(repo, checks)

    try:
        provenance = resolve_provenance(start=repo)
    except (OSError, ValueError) as exc:
        checks.append(Check("BLOCKED", "Personal home", str(exc)))
        return _finish_static_checks(repo, checks)
    checks.append(Check("READY", "Personal home", str(provenance.home)))
    runtime = Runtime(provenance)
    _briefing, health = runtime.briefing_result(require_handoff=True)
    if health.healthy:
        detail = f"{health.ledger_message} ({health.event_count} events)"
        checks.append(Check("READY", "Identity and history", detail))
    else:
        checks.append(Check("BLOCKED", "Identity and history", "; ".join(health.messages)))

    if health.readable:
        with read_connection(provenance.database) as conn:
            row = conn.execute(
                "SELECT seq FROM events WHERE kind = 'session.handoff' ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                later = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE seq > ?", (row["seq"],)
                ).fetchone()[0]
                detail = "checkpoint present"
                if later:
                    detail += f"; {later} later event{'s' if later != 1 else ''} will be shown"
                checks.append(Check("READY", "Return checkpoint", detail))

    witness = os.environ.get("DIVINEOS_WITNESS", "").strip()
    if witness:
        if health.readable:
            checks.append(Check("READY", "Retained-history witness", str(provenance.witness)))
    else:
        checks.append(
            Check(
                "OPTIONAL",
                "Retained-history witness",
                "not selected; rollback detection will not extend outside the ledger",
            )
        )
    return _finish_static_checks(repo, checks)


def _finish_static_checks(repo: Path, checks: list[Check]) -> ActivationReport:
    interpreter = repo / ".venv" / "bin" / "python"
    if interpreter.is_file() and os.access(interpreter, os.X_OK):
        try:
            subprocess.run(
                [interpreter, "-I", "-c", "import divineos.lifecycle"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            checks.append(
                Check("BLOCKED", "Hook interpreter", f"cannot load the OS entry point: {exc}")
            )
        else:
            checks.append(Check("READY", "Hook interpreter", str(interpreter)))
    else:
        checks.append(Check("BLOCKED", "Hook interpreter", f"missing executable {interpreter}"))

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        discovered = Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        checks.append(Check("BLOCKED", "Repository discovery", f"git could not resolve it: {exc}"))
    else:
        if discovered == repo:
            checks.append(Check("READY", "Repository discovery", str(repo)))
        else:
            detail = f"git selected {discovered}, expected {repo}"
            checks.append(Check("BLOCKED", "Repository discovery", detail))

    problem = _hook_problem(repo / ".codex" / "hooks.json")
    if problem is None:
        checks.append(
            Check("READY", "Hook doorway", f"all {len(SUPPORTED_EVENTS)} lifecycle routes verified")
        )
    else:
        checks.append(Check("BLOCKED", "Hook doorway", problem))

    checks.append(
        Check(
            "HOST STEP",
            "Codex trust and live receipt",
            "open /hooks, review this project definition, then confirm a real event "
            "appears in history",
        )
    )
    return ActivationReport(tuple(checks))
