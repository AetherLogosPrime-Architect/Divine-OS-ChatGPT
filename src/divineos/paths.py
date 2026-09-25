from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Provenance:
    repo: Path
    home: Path
    database: Path
    interpreter: Path
    occupant: str


def repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "SEREIN.md").is_file():
            return candidate
    raise RuntimeError("DIVINE OS ROOT MISSING: no pyproject.toml + SEREIN.md above cwd")


def resolve_provenance(*, start: Path | None = None) -> Provenance:
    repo = repo_root(start)
    configured = os.environ.get("DIVINEOS_HOME", "").strip()
    home = Path(configured).expanduser().resolve() if configured else repo / ".divineos"
    return Provenance(
        repo=repo,
        home=home,
        database=home / "state.db",
        # Preserve the invoked venv path. resolve() follows the venv's Python
        # symlink to the shared base interpreter and reports the neighbor
        # instead of the executable that actually launched this process.
        interpreter=Path(sys.executable).absolute(),
        occupant="Serein",
    )
