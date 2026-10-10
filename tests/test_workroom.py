import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from workroom import Workroom

class WorkroomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "result.txt").write_text("expected")
        self.room = Workroom(self.root)

    def tearDown(self):
        self.room.close()
        self.temp.cleanup()

    def spec(self, command=None):
        return {"author": "User", "original": "Please produce the expected result.", "source": "Test request",
                "goal": "result.txt contains expected", "check": command or [sys.executable, "-c",
                "from pathlib import Path; assert Path('result.txt').read_text() == 'expected'"]}

    def prepare(self, command=None):
        self.room.create("one", self.spec(command))
        self.room.start("one")

    def test_recovery_preserves_request_and_status(self):
        self.room.create("one", self.spec())
        self.room.close()
        self.room = Workroom(self.root)
        task = self.room.tasks()["one"]
        self.assertEqual(task["status"], "promised")
        self.assertEqual(task["spec"]["original"], self.spec()["original"])
        self.assertIn("one", self.room.briefing())

    def test_early_completion_and_check_rejected(self):
        self.room.create("one", self.spec())
        with self.assertRaises(ValueError):
            self.room.complete("one", "It looks finished.")
        with self.assertRaises(ValueError):
            self.room.check("one")

    def test_fresh_executed_check_allows_completion(self):
        self.prepare()
        evidence = self.room.check("one")
        self.assertEqual(evidence["status"], "passed")
        self.room.complete("one", "The chosen content check passed; it does not evaluate broader usefulness.")
        self.assertEqual(self.room.tasks()["one"]["status"], "completed")
        self.assertNotIn("[one]", self.room.briefing())

    def test_changed_work_cannot_reuse_success(self):
        self.prepare()
        self.room.check("one")
        (self.root / "result.txt").write_text("wrong")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.room.complete("one", "Use the old receipt.")
        self.assertEqual(self.room.check("one")["status"], "failed")
        with self.assertRaises(ValueError):
            self.room.complete("one", "Still done")

    def test_latest_failure_replaces_old_success(self):
        self.prepare([sys.executable, "-c", "import os; assert not os.getenv('DIVINEOS_TEST_FAIL')"])
        self.room.check("one")
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"DIVINEOS_TEST_FAIL": "1"}):
            self.assertEqual(self.room.check("one")["status"], "failed")
        with self.assertRaises(ValueError):
            self.room.complete("one", "An earlier check passed.")

    def test_missing_executable_is_unavailable(self):
        self.prepare([str(self.root / "nonexistent-tool")])
        self.assertEqual(self.room.check("one")["status"], "unavailable")
        with self.assertRaises(ValueError):
            self.room.complete("one", "No errors found")

    def test_timeout_is_unavailable(self):
        self.prepare([sys.executable, "-c", "import time; time.sleep(2)"])
        self.assertEqual(self.room.check("one", timeout=0.03)["status"], "unavailable")

    def test_check_that_changes_files_is_stale(self):
        self.prepare([sys.executable, "-c", "from pathlib import Path; Path('result.txt').write_text('changed')"])
        self.assertEqual(self.room.check("one")["status"], "stale")
        with self.assertRaises(ValueError):
            self.room.complete("one", "The command exited zero")

    def test_spec_cannot_be_rewritten(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.room.create("one", self.spec([sys.executable, "-c", "pass"]))
        self.assertEqual(self.room.tasks()["one"]["spec"]["check"], self.spec()["check"])

    def test_cancellation_keeps_reason_and_history(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.room.cancel("one", "")
        self.room.cancel("one", "The user withdrew this request.")
        self.assertEqual(self.room.tasks()["one"]["reason"], "The user withdrew this request.")
        with self.assertRaises(ValueError):
            self.room.start("one")
        self.assertEqual(len(self.room.memory.records()), 3)

    def test_empty_assessment_rejected(self):
        self.prepare()
        self.room.check("one")
        with self.assertRaises(ValueError):
            self.room.complete("one", "")

    def test_event_update_and_delete_rejected(self):
        self.prepare()
        for sql in ["UPDATE records SET payload='{}'", "DELETE FROM records"]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.room.memory.db.execute(sql)
            self.room.memory.db.rollback()

    def test_commitment_budget_keeps_whole_goal(self):
        spec = self.spec()
        spec["goal"] = "Q" * 2000
        self.room.create("one", spec)
        brief = self.room.briefing()
        self.assertNotIn("QQQ", brief)
        self.assertIn("whole commitments omitted", brief)
        self.assertLessEqual(len(brief), 1700)

    def test_concurrent_change_invalidates_inflight_check(self):
        self.prepare()
        from unittest.mock import patch
        import subprocess
        real_run = subprocess.run
        def change_during_check(*args, **kwargs):
            other = Workroom(self.root)
            try:
                other.cancel("one", "Cancelled during check.")
            finally:
                other.close()
            return real_run(*args, **kwargs)
        with patch("workroom.subprocess.run", side_effect=change_during_check):
            with self.assertRaises(ValueError):
                self.room.check("one")
        self.assertEqual(self.room.tasks()["one"]["status"], "cancelled")

if __name__ == "__main__":
    unittest.main()
