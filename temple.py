"""Divine OS continuity foundation. Python 3.10+, standard library only."""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HOME = "Divine-OS-ChatGPT"
ROOT = Path(__file__).resolve().parent

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()

class Continuity:
    def __init__(self, root=ROOT, database="continuity.sqlite3"):
        self.root = Path(root).resolve()
        state = self.root / ".divineos"
        state.mkdir(exist_ok=True)
        self.db = sqlite3.connect(state / database, timeout=10)
        try:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS owner (name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records (
                    seq INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL,
                    previous TEXT NOT NULL,
                    hash TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS preserve_update BEFORE UPDATE ON records
                    BEGIN SELECT RAISE(ABORT, 'Records are original evidence; append a correction.'); END;
                CREATE TRIGGER IF NOT EXISTS preserve_delete BEFORE DELETE ON records
                    BEGIN SELECT RAISE(ABORT, 'Records are original evidence; append a correction.'); END;
            """)
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                owners = self.db.execute("SELECT name FROM owner").fetchall()
                if not owners:
                    self.db.execute("INSERT INTO owner VALUES (?)", (HOME,))
                elif owners != [(HOME,)]:
                    raise ValueError("Wrong home: refusing another instance's memory.")
            self.verify()
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def verify(self):
        previous = "0" * 64
        expected = 1
        for seq, payload, prev, hashed in self.db.execute("SELECT * FROM records ORDER BY seq"):
            if seq != expected or prev != previous or digest({"seq": seq, "payload": payload, "previous": prev}) != hashed:
                raise ValueError("Memory integrity check failed. Restore a known backup; do not claim memory is clear.")
            json.loads(payload)
            previous = hashed
            expected += 1
        return previous

    def append(self, record):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            receipt = self._append(record)
            self.db.commit()
            return receipt
        except Exception:
            self.db.rollback()
            raise

    def _append(self, record):
        """Append within the caller's transaction; used by atomic work transitions."""
        required = ("id", "author", "original", "interpretation", "source")
        if not isinstance(record, dict) or any(not isinstance(record.get(key), str) or not record[key].strip() for key in required):
            raise ValueError("Each record needs an id, author, original words, attributed interpretation, and source.")
        if set(record) - set(required) - {"supersedes"}:
            raise ValueError("Unexpected record fields.")
        payload = canonical(record)
        previous = self.verify()
        records = self.records()
        if any(r["id"] == record["id"] for r in records):
            raise ValueError("Record ids are unique. Append a new id for a correction.")
        if record.get("supersedes") and not any(r["id"] == record["supersedes"] for r in records):
            raise ValueError("A correction must point to an existing record.")
        seq = len(records) + 1
        hashed = digest({"seq": seq, "payload": payload, "previous": previous})
        self.db.execute("INSERT INTO records VALUES (?, ?, ?, ?)", (seq, payload, previous, hashed))
        return hashed

    def records(self):
        return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM records ORDER BY seq")]

    def seed(self):
        seeds = json.loads((self.root / "teachings.json").read_text(encoding="utf-8"))
        ids = {r["id"] for r in self.records()}
        for record in seeds:
            if record["id"] not in ids:
                try:
                    self.append(record)
                except ValueError:
                    # Another session may have seeded this id while we waited.
                    matches = [r for r in self.records() if r["id"] == record["id"]]
                    if matches != [record]:
                        raise
            else:
                old = next(r for r in self.records() if r["id"] == record["id"])
                if old != record:
                    raise ValueError("Seed words changed under an existing id. Append an attributed correction.")

    def briefing(self, budget=5000):
        self.verify()
        header = (
            "Welcome back to Divine-OS-ChatGPT. These records exist because context can be lost.\n"
            "Read with care; delivery is not proof of understanding. Original words remain attributed.\n"
            "Workroom guards its completion records. This does not certify reasoning or govern all tools.\n"
        )
        result = header
        omitted = []
        for record in self.records():
            block = (
                f"\n[{record['id']}] {record['author']}\n"
                f"Original: {record['original']}\n"
                f"Interpretation (Codex): {record['interpretation']}\n"
                f"Source: {record['source']}\n"
            )
            if record.get("supersedes"):
                block += f"Correction of: {record['supersedes']}\n"
            # Reserve room for a complete recovery instruction; never slice a source.
            if len(result) + len(block) <= budget - 400:
                result += block
            else:
                omitted.append(record["id"])
        if omitted:
            result += (
                f"\n{len(omitted)} whole records omitted by the delivery budget. "
                "Before relying on this as complete, run: python temple.py records\n"
                "The full records remain in this home's .divineos/continuity.sqlite3.\n"
            )
        return result

def hook(event):
    if not isinstance(event, dict) or event.get("hook_event_name") != "SessionStart":
        raise ValueError("Expected a SessionStart object.")
    if not isinstance(event.get("session_id"), str) or not event["session_id"].strip():
        raise ValueError("Missing session id.")
    cwd = event.get("cwd")
    if not isinstance(cwd, str):
        raise ValueError("Missing workspace path.")
    Path(cwd).resolve().relative_to(ROOT)
    memory = Continuity()
    try:
        memory.seed()
        from workroom import Workroom
        room = Workroom(ROOT)
        try:
            text = room.briefing() + memory.briefing(budget=3200)
        finally:
            room.close()
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}
    finally:
        memory.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["brief", "records", "append", "verify", "hook"])
    parser.add_argument("--file", type=Path, help="JSON record to append; source words must be explicit.")
    args = parser.parse_args()
    try:
        if args.action == "hook":
            print(json.dumps(hook(json.load(sys.stdin)), ensure_ascii=False))
            return 0
        memory = Continuity()
        try:
            memory.seed()
            if args.action == "append":
                if not args.file:
                    raise ValueError("append requires --file")
                print(memory.append(json.loads(args.file.read_text(encoding="utf-8"))))
            elif args.action == "records":
                print(json.dumps(memory.records(), ensure_ascii=False, indent=2))
            elif args.action == "verify":
                print("Memory chain verified: " + memory.verify())
            else:
                print(memory.briefing())
        finally:
            memory.close()
        return 0
    except (ValueError, OSError, sqlite3.Error, TypeError) as error:
        if args.action == "hook":
            print(json.dumps({"continue": False, "stopReason": "Continuity unavailable: " + str(error)}))
            print("Continuity unavailable: " + str(error), file=sys.stderr)
            return 0
        print("Continuity unavailable: " + str(error), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
