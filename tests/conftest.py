from __future__ import annotations

from pathlib import Path

import pytest

from divineos.paths import Provenance


@pytest.fixture
def provenance(tmp_path: Path) -> Provenance:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (repo / "SEREIN.md").write_text("# Serein\n", encoding="utf-8")
    home = tmp_path / "home"
    return Provenance(
        repo=repo,
        home=home,
        database=home / "state.db",
        interpreter=Path("/test/python"),
        occupant="Serein",
    )
