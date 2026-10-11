from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from divineos.delivery import deliver, relevant_passage
from divineos.paths import Provenance
from divineos.runtime import Runtime
from divineos.store import connect


REPO = Path(__file__).resolve().parents[1]


class PassageDeliveryTests(unittest.TestCase):
    def test_complete_paragraphs_preserve_nearby_qualification(self):
        text = (
            "Unrelated orchard notes.\n\n"
            "Only apply this during ordinary conversation.\n\n"
            "Return from technical work to our shared conversation.\n\n"
            "Keep technical detail when Andrew explicitly asks for it.\n\n"
            "Unrelated kitchen notes."
        )
        span = relevant_passage(text, {"technical", "conversation", "shared"})
        self.assertIsNotNone(span)
        start, end = span
        excerpt = text[start:end]
        self.assertIn("Only apply", excerpt)
        self.assertIn("explicitly asks", excerpt)
        self.assertNotIn("orchard", excerpt)
        self.assertNotIn("kitchen", excerpt)

    def test_words_in_separate_paragraphs_do_not_make_a_match(self):
        self.assertIsNone(
            relevant_passage("orchard apples\n\nengine repairs", {"apples", "engine"})
        )

    def test_actual_delivery_and_full_source_read_with_integrity_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            runtime = Runtime(
                Provenance(REPO, home, home / "state.db", Path(sys.executable), "Serein")
            )
            runtime.initialize()
            original = "\n\n".join(
                [
                    "Unrelated beginning " * 80,
                    "This lesson applies when returning to Andrew.",
                    "Explain technical work from the shared conversation.",
                    "Andrew chooses how far to explore the details.",
                    "Unrelated ending " * 80,
                ]
            ).strip()
            memory_id = runtime.remember(original, "synthetic conversation receipt")
            for number in range(5):
                runtime.remember(f"Recent unrelated note {number}", "fixture")
            runtime.record_handoff(
                {
                    "completed": [],
                    "unfinished": [],
                    "blocked": [],
                    "decisions": [],
                    "next_step": "Test passage delivery",
                }
            )
            request = {"session_id": "passages", "hook_event_name": "SessionStart"}
            deliver(runtime, request)
            request.update(
                hook_event_name="UserPromptSubmit", prompt="technical shared conversation"
            )
            result = deliver(runtime, request)
            self.assertIn("Andrew chooses", result)
            self.assertIn(f"divineos memory show {memory_id}", result)
            self.assertIn("other context may exist", result)
            self.assertNotIn("Unrelated beginning", result)
            self.assertNotIn("Unrelated ending", result)
            self.assertIsNone(deliver(runtime, request))
            env = dict(os.environ, DIVINEOS_HOME=str(home), PYTHONPATH=str(REPO / "src"))
            read = subprocess.run(
                [sys.executable, "-m", "divineos.cli", "memory", "show", memory_id],
                cwd=REPO,
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(read.returncode, 0, read.stderr)
            self.assertEqual(json.loads(read.stdout)["text"], original)
            with connect(runtime.provenance.database) as conn:
                conn.execute(
                    "UPDATE memories SET text = 'tampered' WHERE memory_id = ?", (memory_id,)
                )
            with self.assertRaises(RuntimeError):
                runtime.memory(memory_id)


if __name__ == "__main__":
    unittest.main()
