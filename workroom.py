"""Recover commitments and require fresh executed evidence before closing work."""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from temple import ROOT, Continuity, canonical, digest

IGNORED = {".git", ".divineos", "__pycache__"}
TERMINAL = {"completed", "cancelled"}

def snapshot(root):
    """Hash the work tree, excluding runtime state and Git metadata."""
    root = Path(root).resolve()
    files = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            if name not in IGNORED and (Path(current) / name).is_symlink():
                raise ValueError("Evidence scope contains a directory symlink.")
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in sorted(names):
            path = Path(current) / name
            if path.is_symlink():
                raise ValueError("Evidence scope contains a file symlink.")
            import hashlib
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(65536), b""):
                    hasher.update(chunk)
            files[path.relative_to(root).as_posix()] = hasher.hexdigest()
    return digest(files)

class Workroom:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.memory = Continuity(self.root, database="work.sqlite3")

    def close(self):
        self.memory.close()

    def tasks(self):
        self.memory.verify()
        result = {}
        for record in self.memory.records():
            event = json.loads(record["original"])
            task_id = event["task"]
            kind = event["kind"]
            if kind == "create":
                if task_id in result:
                    raise ValueError("Work history has duplicate commitments.")
                result[task_id] = {"id": task_id, "spec": event["data"], "status": "promised", "evidence": None}
            else:
                if task_id not in result:
                    raise ValueError("Work history refers to an unknown commitment.")
                task = result[task_id]
                if task["status"] in TERMINAL:
                    raise ValueError("Work history changes a closed commitment.")
                if kind == "start":
                    task["status"] = "active"
                elif kind == "check":
                    task["evidence"] = event["data"]
                    task["status"] = "checked" if event["data"]["status"] == "passed" else "active"
                elif kind == "complete":
                    task["status"] = "completed"
                    task["assessment"] = event["data"]["assessment"]
                elif kind == "cancel":
                    task["status"] = "cancelled"
                    task["reason"] = event["data"]["reason"]
                else:
                    raise ValueError("Unknown work event.")
            result[task_id]["revision"] = record["id"]
        return result

    def _write(self, kind, task_id, data, validate):
        db = self.memory.db
        db.execute("BEGIN IMMEDIATE")
        try:
            tasks = self.tasks()
            validate(tasks)
            self.memory._append({
                "id": str(uuid.uuid4()), "author": "Codex workroom",
                "original": canonical({"kind": kind, "task": task_id, "data": data}),
                "interpretation": "Recorded workflow event; checks do not certify understanding.",
                "source": "Local workroom interface",
            })
            db.commit()
        except Exception:
            db.rollback()
            raise

    def create(self, task_id, spec):
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("A commitment needs an id.")
        required = {"author", "original", "source", "goal", "check"}
        if not isinstance(spec, dict) or set(spec) != required:
            raise ValueError("Commitment requires author, original request, source, goal, and check argv.")
        if any(not isinstance(spec[k], str) or not spec[k].strip() for k in required - {"check"}):
            raise ValueError("Keep the request, attribution and intended outcome explicit.")
        if not isinstance(spec["check"], list) or not spec["check"] or any(not isinstance(s, str) or not s or "\0" in s for s in spec["check"]):
            raise ValueError("Check must be an explicit argv list, without shell composition.")
        def validate(tasks):
            if task_id in tasks:
                raise ValueError("Existing commitments cannot be rewritten. Cancel with a reason and create a new id.")
        self._write("create", task_id, spec, validate)

    def _open(self, tasks, task_id):
        if task_id not in tasks:
            raise ValueError("Unknown commitment.")
        if tasks[task_id]["status"] in TERMINAL:
            raise ValueError("This commitment is closed.")
        return tasks[task_id]

    def start(self, task_id):
        self._write("start", task_id, {}, lambda tasks: self._open(tasks, task_id))

    def check(self, task_id, timeout=30):
        task = self._open(self.tasks(), task_id)
        if task["status"] == "promised":
            raise ValueError("Start the commitment before checking work.")
        before = snapshot(self.root)
        evidence = {"status": "unavailable", "command": task["spec"]["check"], "before": before}
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                completed = subprocess.run(task["spec"]["check"], cwd=self.root, shell=False,
                                           stdout=out, stderr=err, timeout=timeout)
                evidence.update(returncode=completed.returncode,
                                status="passed" if completed.returncode == 0 else "failed")
            except (OSError, subprocess.TimeoutExpired) as error:
                evidence["error"] = str(error)
            for name, stream in (("stdout", out), ("stderr", err)):
                size = stream.tell()
                stream.seek(0)
                evidence[name] = stream.read(4096).decode("utf-8", errors="replace")
                evidence[name + "_omitted_bytes"] = max(0, size - 4096)
        evidence["after"] = snapshot(self.root)
        if evidence["before"] != evidence["after"]:
            evidence["status"] = "stale"
        def validate(tasks):
            current = self._open(tasks, task_id)
            if current["revision"] != task["revision"]:
                raise ValueError("Commitment changed while checking. Run a fresh check.")
        self._write("check", task_id, evidence, validate)
        return evidence

    def complete(self, task_id, assessment):
        if not isinstance(assessment, str) or not assessment.strip():
            raise ValueError("Explain how the result addresses the commitment, including remaining limits.")
        current_tree = snapshot(self.root)
        def validate(tasks):
            task = self._open(tasks, task_id)
            evidence = task["evidence"]
            if task["status"] != "checked" or not evidence or evidence["status"] != "passed":
                raise ValueError("Completion requires the latest executed check to pass.")
            if evidence["after"] != current_tree:
                raise ValueError("The work changed after verification. Run a fresh check.")
        self._write("complete", task_id, {"assessment": assessment}, validate)

    def cancel(self, task_id, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Cancelling a commitment needs an explicit reason.")
        self._write("cancel", task_id, {"reason": reason}, lambda tasks: self._open(tasks, task_id))

    def briefing(self, budget=1700):
        tasks = [t for t in self.tasks().values() if t["status"] not in TERMINAL]
        result = "\nUnfinished commitments:\n"
        omitted = 0
        for task in tasks:
            block = f"[{task['id']}] {task['status']}: {task['spec']['goal']}\n"
            if len(result) + len(block) <= budget - 200:
                result += block
            else:
                omitted += 1
        if not tasks:
            result += "No unfinished commitments recorded. This is not proof that all promises were captured.\n"
        if omitted:
            result += f"{omitted} whole commitments omitted. Recover all with: python workroom.py list\n"
        result += "For original requests, checks and history: python workroom.py list\n"
        return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "start", "check", "complete", "cancel", "list", "brief"])
    parser.add_argument("id", nargs="?")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--note", help="Assessment for completion or reason for cancellation.")
    args = parser.parse_args()
    room = None
    try:
        room = Workroom()
        if args.action == "create":
            if not args.file:
                raise ValueError("create requires --file with an attributed commitment specification.")
            room.create(args.id, json.loads(args.file.read_text(encoding="utf-8")))
        elif args.action == "start":
            room.start(args.id)
        elif args.action == "check":
            evidence = room.check(args.id)
            print(json.dumps(evidence, ensure_ascii=False, indent=2))
            return 0 if evidence["status"] == "passed" else 1
        elif args.action == "complete":
            room.complete(args.id, args.note)
        elif args.action == "cancel":
            room.cancel(args.id, args.note)
        elif args.action == "list":
            print(json.dumps(room.tasks(), ensure_ascii=False, indent=2))
        else:
            print(room.briefing())
        return 0
    except (ValueError, OSError, sqlite3.Error, TypeError, KeyError) as error:
        print("Work recovery unavailable: " + str(error), file=sys.stderr)
        return 1
    finally:
        if room:
            room.close()

if __name__ == "__main__":
    sys.exit(main())
