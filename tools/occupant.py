"""Use DivineOS memory in a separate, explicitly owned local profile.

This adapter uses the supplied OS source; it does not implement another memory
store. Its Python audit guard catches accidental out-of-profile writes, database
opens, subprocesses, and network connections. It is NOT an OS security sandbox
and is unsuitable for hostile code or unreviewed native extensions.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import hashlib
import json
import os
from pathlib import Path
import sys


class BoundaryViolation(RuntimeError):
    pass


def apply_setup(setup, profile, state, ledger, memory):
    """Adopt a declared setup, retaining the provenance of example-derived lessons.

    Validate the entire input before writes. A completed repeat is a no-op.
    Individual upstream writes are durable but this multi-API operation is not
    one transaction; after interruption, retry may add another attempt event.
    """
    from divineos.core.knowledge.crud import find_similar, store_knowledge

    if not isinstance(setup, dict) or setup.get("version") != 1:
        raise ValueError("Unsupported setup format")
    if setup.get("name") != profile["name"]:
        raise ValueError("Setup name does not match this occupant")
    core = setup.get("core")
    lessons = setup.get("lessons")
    if not isinstance(core, dict) or not isinstance(lessons, list):
        raise ValueError("Setup requires core and lessons")
    if core.get("my_identity") != profile["name"]:
        raise ValueError("Setup must preserve this occupant's identity")
    for slot, value in core.items():
        if slot not in memory.CORE_SLOTS or not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid core-memory slot or value: {slot}")
    seen = set()
    for lesson in lessons:
        if not isinstance(lesson, dict):
            raise ValueError("Every lesson must be an object")
        for key in ("id", "content", "origin"):
            if not isinstance(lesson.get(key), str) or not lesson[key].strip():
                raise ValueError(f"Lesson needs a nonempty {key}")
        if lesson["id"] in seen or len(lesson["content"].strip()) < 5:
            raise ValueError("Duplicate lesson ID or insufficient content")
        seen.add(lesson["id"])
        refs = lesson.get("references")
        if not isinstance(refs, list) or not refs or not all(isinstance(x, str) and x.strip() for x in refs):
            raise ValueError("Every inherited lesson needs source references")
        for existing in find_similar(lesson["content"]):
            if existing.get("source") != "INHERITED" or existing.get("source_entity") != lesson["origin"]:
                raise ValueError("Existing knowledge has different provenance; refusing to relabel it")

    digest = hashlib.sha256(json.dumps(setup, sort_keys=True).encode("utf-8")).hexdigest()
    receipt_path = state / "applied_setups.json"
    receipts = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
    if digest in receipts:
        return {"status": "already_applied", "digest": digest, "receipt": receipts[digest]}

    event = ledger.log_event("OCCUPANT_SETUP", "assistant", {
        "name": profile["name"], "digest": digest, "core": core,
        "inherited_lessons": lessons, "provenance": "selective adaptation from source examples",
    })
    current = memory.get_core()
    for slot, value in core.items():
        if current.get(slot) != value:
            memory.set_core(slot, value)
    ids = []
    for lesson in lessons:
        kid = store_knowledge(
            "PROCEDURE", lesson["content"], confidence=0.5,
            source_events=[event], source="INHERITED", maturity="RAW",
            source_entity=lesson["origin"], memory_kind="PROCEDURAL",
            tags=["inherited-practice", lesson["id"]],
        )
        if not kid:
            raise ValueError("A lesson was previously superseded; it will not be resurrected")
        ids.append(kid)
    receipts[digest] = {"event_id": event, "knowledge_ids": ids}
    temporary = state / "applied_setups.json.tmp"
    temporary.write_text(json.dumps(receipts, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt_path)
    return {"status": "applied", "digest": digest, "receipt": receipts[digest], "core": memory.get_core()}


def within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def write_guard(root: Path, violations: list[str]):
    def refuse(message: str):
        violations.append(message)
        raise BoundaryViolation(message)

    def check(path):
        if isinstance(path, int):
            return
        if not within(Path(os.fsdecode(path)), root):
            refuse(f"Write or database access outside occupant profile: {path}")

    def audit(event, args):
        if event == "open":
            path, mode, flags = args
            if (mode and any(c in mode for c in "wax+")) or (
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            ):
                check(path)
        elif event == "sqlite3.connect":
            if str(args[0]) != ":memory:":
                # URI paths require separate parsing; this adapter never uses them.
                if str(args[0]).startswith("file:"):
                    refuse("SQLite URI connections are not supported in this profile")
                check(args[0])
        elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
            check(args[0])
        elif event in {"os.rename", "os.link"}:
            check(args[0])
            check(args[1])
        elif event == "os.symlink":
            refuse("Creating links inside the profile is not supported")
        elif event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "socket.connect", "socket.bind"}:
            refuse(f"External operation disabled for this adapter: {event}")

    return audit


def configure(source: Path, state: Path, action: str, name: str | None):
    source, state = source.resolve(), state.resolve()
    if not (source / "src/divineos/core/ledger.py").is_file():
        raise ValueError("--source must be a DivineOS checkout containing src/divineos")
    if within(state, source) or within(source, state):
        raise ValueError("Source and occupant profile must be separate, non-overlapping directories")
    manifest = state / "occupant.json"
    if manifest.exists():
        profile = json.loads(manifest.read_text(encoding="utf-8"))
        if profile.get("adapter") != "divineos-chatgpt-v1":
            raise ValueError("Unrecognized occupant profile")
        if profile.get("state") != str(state) or profile.get("source") != str(source):
            raise ValueError("Profile belongs to a different source or state path")
        if name is not None and profile.get("name") != name:
            raise ValueError("Refusing to overwrite another occupant's identity")
    elif action != "bootstrap":
        raise ValueError("Profile is not initialized; run bootstrap --name first")
    else:
        if not name or not name.strip():
            raise ValueError("bootstrap requires a nonempty --name")
        if state.exists() and any(state.iterdir()):
            raise ValueError("Refusing to initialize a nonempty, unowned directory")
        state.mkdir(parents=True, exist_ok=True)
        profile = {"adapter": "divineos-chatgpt-v1", "name": name.strip(),
                   "source": str(source), "state": str(state), "seed_policy": "no inherited personal state"}
        manifest.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")

    for rel in ["data", "tmp", "user", "cache"]:
        (state / rel).mkdir(exist_ok=True)
    # Do not inherit routing, session identity, bypass flags, or installed paths.
    for key in list(os.environ):
        if key.startswith(("DIVINEOS_", "CLAUDE_", "PYTHON")):
            del os.environ[key]
    os.environ.update({
        "DIVINEOS_HOME": str(state),
        "DIVINEOS_DB": str(state / "data/event_ledger.db"),
        "DIVINEOS_FAMILY_DB": str(state / "data/family.db"),
        "DIVINEOS_SKIP_EMBED_ON_WRITE": "1",
        "DIVINEOS_LOG_LEVEL": "WARNING",
        "HOME": str(state / "user"), "USERPROFILE": str(state / "user"),
        "APPDATA": str(state / "user"), "LOCALAPPDATA": str(state / "user"),
        "TMP": str(state / "tmp"), "TEMP": str(state / "tmp"), "TMPDIR": str(state / "tmp"),
        "XDG_CACHE_HOME": str(state / "cache"), "HF_HOME": str(state / "cache"),
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
    })
    # Overrides above affect only this child process, never the user's shell.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / "src"))
    os.chdir(state)
    return profile


def operate(args):
    # Read explicit configuration before changing the working directory.
    setup = json.loads(args.setup.read_text(encoding="utf-8-sig")) if args.setup else None
    profile = configure(args.source, args.state, args.action, args.name)
    state = args.state.resolve()
    violations: list[str] = []
    sys.addaudithook(write_guard(state, violations))

    from divineos.core import ledger, memory
    from divineos.core._ledger_base import _get_db_path
    from divineos.core.paths import divineos_home
    from divineos.core.family.db import _get_family_db_path

    if not within(Path(ledger.__file__), args.source / "src"):
        raise BoundaryViolation("Imported ledger does not belong to the requested source")
    resolved = {"home": str(divineos_home().resolve()), "ledger": str(_get_db_path().resolve()),
                "family": str(_get_family_db_path().resolve()), "source": str(Path(ledger.__file__).resolve())}
    for key in ("home", "ledger", "family"):
        if not within(Path(resolved[key]), state):
            raise BoundaryViolation(f"Resolved {key} is outside the occupant profile")

    if args.action != "bootstrap" and memory.get_core("my_identity").get("my_identity") != profile["name"]:
        raise ValueError("Stored identity disagrees with profile owner")

    if args.action == "bootstrap":
        ledger.init_db()
        memory.init_memory_tables()
        from divineos.core.knowledge._base import init_knowledge_table
        init_knowledge_table()
        from divineos.core.knowledge.edges import init_edge_table
        from divineos.core.questions import init_questions_table
        init_edge_table()
        init_questions_table()
        core = memory.get_core()
        if core.get("my_identity") and core["my_identity"] != profile["name"]:
            raise ValueError("Stored identity disagrees with profile owner")
        if not core.get("my_identity"):
            memory.set_core("my_identity", profile["name"])
            memory.set_core("project_purpose", "Understand DivineOS, use its working systems, and develop a portable fresh-occupant foundation.")
            memory.set_core("active_constraints", "Inherited records are source material, not this occupant's personal memories. Keep other occupants' stores unchanged.")
            ledger.log_event("OCCUPANT_BOOTSTRAP", "assistant", {"name": profile["name"], "seed_policy": profile["seed_policy"]})
        result = {"profile": profile, "resolved": resolved, "core": memory.get_core()}
    elif args.action == "adopt-setup":
        if setup is None:
            raise ValueError("adopt-setup requires --setup")
        result = apply_setup(setup, profile, state, ledger, memory)
    elif args.action == "remember":
        from divineos.core.knowledge.crud import store_knowledge
        if not args.text:
            raise ValueError("remember requires --text")
        if memory.get_core("my_identity").get("my_identity") != profile["name"]:
            raise ValueError("Stored identity disagrees with profile owner")
        event = ledger.log_event("OCCUPANT_NOTE", "assistant", {"content": args.text, "source": args.basis})
        kid = store_knowledge("OBSERVATION", args.text, confidence=args.confidence,
                              source_events=[event], source=args.basis, maturity="RAW",
                              source_entity=profile["name"], tags=["occupant-notes"], memory_kind="EPISODIC")
        result = {"knowledge_id": kid, "event_id": event}
    elif args.action == "recall":
        from divineos.core.knowledge.crud import search_knowledge
        result = {"matches": search_knowledge(args.query or "", limit=20)}
    elif args.action == "briefing":
        from divineos.core.knowledge.crud import get_knowledge
        # Explicitly constructed from the real stores; not the full upstream
        # briefing, which loads many personal/host-specific surfaces.
        result = {"kind": "minimal occupant briefing", "core": memory.get_core(),
                  "notes": get_knowledge(limit=20), "resolved": resolved}
    elif args.action == "native-briefing":
        from divineos.core.knowledge import generate_briefing
        text = generate_briefing(max_items=20)
        result = {"kind": "upstream knowledge briefing", "text": text,
                  "reports_incomplete": "Briefing incomplete:" in text, "resolved": resolved}
    elif args.action == "verify":
        result = {"chain": ledger.verify_chain(), "resolved": resolved}
        if not result["chain"]["ok"]:
            raise ValueError(f"Ledger verification failed: {result['chain']}")
    else:
        result = {"resolved": resolved, "profile": profile}

    from loguru import logger
    logger.complete()
    logger.remove()
    # An upstream fail-soft handler must not conceal a boundary violation.
    if violations:
        raise BoundaryViolation("; ".join(violations))
    return result


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("action", choices=["bootstrap", "inspect", "adopt-setup", "remember", "recall", "briefing", "native-briefing", "verify"])
    parser.add_argument("--setup", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--text")
    parser.add_argument("--query")
    parser.add_argument("--basis", choices=["STATED", "DEMONSTRATED", "SYNTHESIZED"], default="SYNTHESIZED")
    parser.add_argument("--confidence", type=float, default=0.5)
    args = parser.parse_args()
    if not 0 <= args.confidence <= 1:
        parser.error("--confidence must be between 0 and 1")
    # Resolve before the worker changes directories.
    args.source, args.state = args.source.resolve(), args.state.resolve()
    try:
        with redirect_stdout(sys.stderr):
            result = operate(args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
