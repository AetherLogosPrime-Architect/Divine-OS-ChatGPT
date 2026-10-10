import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import temple

class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copy(temple.ROOT / "teachings.json", self.root / "teachings.json")
        self.memory = temple.Continuity(self.root)

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def record(self, **changes):
        value = dict(id="test", author="User", original="Keep these words.", interpretation="Preserve attribution.", source="Test source")
        value.update(changes)
        return value

    def test_original_and_interpretation_preserved(self):
        record = self.record()
        self.memory.append(record)
        self.assertEqual(self.memory.records(), [record])

    def test_no_overwrite_or_delete(self):
        self.memory.append(self.record())
        for sql in ["UPDATE records SET payload='{}'", "DELETE FROM records"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.memory.db.execute(sql)
            self.memory.db.rollback()
        self.assertEqual(self.memory.records()[0]["original"], "Keep these words.")

    def test_duplicate_rejected(self):
        self.memory.append(self.record())
        with self.assertRaises(ValueError):
            self.memory.append(self.record(original="Rewritten"))
        self.assertEqual(len(self.memory.records()), 1)

    def test_missing_attribution_rejected(self):
        for key in ["id", "author", "original", "interpretation", "source"]:
            with self.assertRaises(ValueError):
                self.memory.append(self.record(**{key: ""}))
        self.assertEqual(self.memory.records(), [])

    def test_correction_preserves_both(self):
        self.memory.append(self.record())
        self.memory.append(self.record(id="correction", original="More precise words.", supersedes="test"))
        self.assertEqual(len(self.memory.records()), 2)
        self.assertEqual(self.memory.records()[0]["original"], "Keep these words.")

    def test_unknown_correction_rejected(self):
        with self.assertRaises(ValueError):
            self.memory.append(self.record(supersedes="missing"))

    def test_seed_idempotent_and_original_changes_rejected(self):
        self.memory.seed()
        before = self.memory.verify()
        self.memory.seed()
        self.assertEqual(self.memory.verify(), before)
        seeds = json.loads((self.root / "teachings.json").read_text())
        seeds[0]["original"] = "Convenient rewrite"
        (self.root / "teachings.json").write_text(json.dumps(seeds))
        with self.assertRaises(ValueError):
            self.memory.seed()

    def test_chain_tamper_detected(self):
        self.memory.append(self.record())
        self.memory.db.execute("DROP TRIGGER preserve_update")
        self.memory.db.execute("UPDATE records SET payload='{}'")
        self.memory.db.commit()
        with self.assertRaisesRegex(ValueError, "integrity"):
            self.memory.verify()

    def test_wrong_owner_rejected(self):
        self.memory.db.execute("UPDATE owner SET name='another home'")
        self.memory.db.commit()
        with self.assertRaisesRegex(ValueError, "Wrong home"):
            temple.Continuity(self.root)

    def test_large_record_not_cut(self):
        self.memory.append(self.record(original="Z" * 6000))
        brief = self.memory.briefing()
        self.assertNotIn("ZZZ", brief)
        self.assertIn("whole records omitted", brief)
        self.assertIn("python temple.py records", brief)
        self.assertLessEqual(len(brief), 5000)
        self.assertEqual(len(self.memory.records()[0]["original"]), 6000)

    def test_reopen_and_isolation(self):
        self.memory.append(self.record())
        self.memory.close()
        self.memory = temple.Continuity(self.root)
        self.assertEqual(len(self.memory.records()), 1)
        with tempfile.TemporaryDirectory() as other:
            second = temple.Continuity(other)
            try:
                self.assertEqual(second.records(), [])
            finally:
                second.close()

class HookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copy(temple.ROOT / "temple.py", self.root / "temple.py")
        shutil.copy(temple.ROOT / "workroom.py", self.root / "workroom.py")
        shutil.copy(temple.ROOT / "teachings.json", self.root / "teachings.json")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, event):
        result = subprocess.run([sys.executable, str(self.root / "temple.py"), "hook"],
                                input=json.dumps(event), text=True, capture_output=True, cwd=self.root)
        return result, json.loads(result.stdout)

    def test_session_start_generates_attributed_context(self):
        result, output = self.invoke(dict(hook_event_name="SessionStart", session_id="one", cwd=str(self.root)))
        self.assertEqual(result.returncode, 0, result.stderr)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Original:", context)
        self.assertIn("Interpretation (Codex):", context)
        self.assertIn("delivery is not proof", context)

    def test_session_start_recovers_unfinished_work(self):
        from workroom import Workroom
        room = Workroom(self.root)
        try:
            room.create("recover-me", {"author": "User", "original": "Keep cooking.", "source": "Test",
                                       "goal": "Recover unfinished work", "check": [sys.executable, "-c", "pass"]})
        finally:
            room.close()
        result, output = self.invoke(dict(hook_event_name="SessionStart", session_id="new-context", cwd=str(self.root)))
        self.assertEqual(result.returncode, 0)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("[recover-me] promised: Recover unfinished work", context)
        self.assertLessEqual(len(context), 5000)

    def test_wrong_workspace_stops(self):
        result, output = self.invoke(dict(hook_event_name="SessionStart", session_id="one", cwd=str(self.root.parent)))
        self.assertFalse(output["continue"])
        self.assertIn("Continuity unavailable", output["stopReason"])

    def test_missing_session_stops(self):
        result, output = self.invoke(dict(hook_event_name="SessionStart", cwd=str(self.root)))
        self.assertFalse(output["continue"])

    def test_invalid_json_stops(self):
        result = subprocess.run([sys.executable, str(self.root / "temple.py"), "hook"],
                                input="{", text=True, capture_output=True, cwd=self.root)
        self.assertFalse(json.loads(result.stdout)["continue"])

if __name__ == "__main__":
    unittest.main()
