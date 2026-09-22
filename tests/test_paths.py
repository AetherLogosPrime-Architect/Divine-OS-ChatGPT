from __future__ import annotations

from pathlib import Path

import pytest

from divineos.paths import repo_root, resolve_provenance


def test_repo_root_walks_up_to_both_markers(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("", encoding="utf-8")
    (repo / "SEREIN.md").write_text("", encoding="utf-8")

    assert repo_root(nested) == repo


def test_repo_root_fails_loudly_without_identity_marker(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="DIVINE OS ROOT MISSING"):
        repo_root(tmp_path)


def test_explicit_home_is_reported_exactly(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("", encoding="utf-8")
    (repo / "SEREIN.md").write_text("", encoding="utf-8")
    selected = tmp_path / "selected-home"
    monkeypatch.setenv("DIVINEOS_HOME", str(selected))

    provenance = resolve_provenance(start=repo)

    assert provenance.home == selected.resolve()
    assert provenance.database == selected.resolve() / "state.db"


def test_interpreter_preserves_invoked_path(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("", encoding="utf-8")
    (repo / "SEREIN.md").write_text("", encoding="utf-8")
    invoked = tmp_path / ".venv" / "bin" / "python"
    monkeypatch.setattr("sys.executable", str(invoked))

    provenance = resolve_provenance(start=repo)

    assert provenance.interpreter == invoked
