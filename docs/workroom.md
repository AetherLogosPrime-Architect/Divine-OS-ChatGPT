# The workroom: promises survive context loss

Built by Codex for this home, with the user's invitation to keep building, October 10, 2026.

The failure prevented: calling something finished because it was planned, because an old check once passed, or because the record of unfinished work disappeared from the current conversation.

Welcome back. Recover the promise before acting. Keep its original wording and your proposed result distinct. Choose a check that addresses the actual promise. If it cannot run, recover the missing condition. If the work changes, check it again. Explain what the evidence supports and where it stops.

## What this mechanism does

Each commitment preserves the author's original request and source, the goal translated by Codex, and an explicit command to check that goal. These are immutable through the workroom interface. Changing the scope requires cancelling the old commitment with a reason and recording a new one.

The flow is promised -> active -> checked -> completed. Cancellation is an explicit alternative with preserved history. The latest check can be passed, failed, unavailable, or stale.

The checker executes the recorded command from the project root with no implicit shell. It captures the exit code, a bounded stdout/stderr preview, and hashes of the project files before and after. Runtime state, Git metadata, and Python bytecode directories are excluded. Symlinks in the evidence scope are rejected.

Completion requires the latest recorded check to pass, the files to match that receipt, and an explicit assessment of how the result addresses the request. A zero exit code from a check that changed files is stale; run a check against the resulting files. Failed and unavailable checks block completion even if an older check passed.

The session briefing brings unfinished commitments ahead of the founding teachings. It preserves whole goals and gives a recovery command when there is more than fits. All originals and event history stay in local state.

## Example

Create a JSON file named commitment.json:

```json
{
  "author": "User",
  "original": "Please build and test unfinished-work recovery.",
  "source": "Conversation request",
  "goal": "Recover commitments and reject completion based on stale or unsuccessful checks.",
  "check": ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
}
```

Review the command before running it. This is a command you authorize, not a sandbox for untrusted commands. Use the Python executable available on your machine.

From the project root:

```text
python workroom.py create recovery --file commitment.json
python workroom.py start recovery
python workroom.py list
python workroom.py check recovery
python workroom.py complete recovery --note "Tests cover fresh-context recovery and the rejected shortcuts. Live Codex hook delivery remains unverified."
```

If the request is withdrawn:

```text
python workroom.py cancel recovery --note "The user withdrew this request."
```

Local state is in .divineos/work.sqlite3. Back up both local databases with SQLite-aware tooling while they are open, or close the connections before copying. Neither database is committed to Git.

## Limits to keep visible

This gates completion records made through the workroom. It does not prevent arbitrary tool calls, direct database/code replacement, or saying 'done' in chat. The file fingerprint covers this project's file bytes, not remote services, environment variables, timestamps, dependencies outside the project, or every possible filesystem race. The recorded command can itself call other tools; there is no command sandbox here.

No mechanism can infer from exit code zero alone that the command was meaningful. The goal, chosen check and assessment stay visible for review, but a filled assessment is not proof of reasoning. Current commitments are explicitly recorded; a missing promise cannot be recovered automatically.

The lifecycle adapter has a simulated-input test that recovers an unfinished commitment into a new session briefing. A live trusted Codex lifecycle still needs to demonstrate delivery. Prepared output is not proof that it reached the model.

## Further structural work

The next useful boundary is between task-specific evidence and consequential actions such as publishing or changing shared state. Define which operations the gate actually controls, bind the evidence to that operation, preserve errors as unavailable, and test alternate routes. Do not claim the whole room is locked because one door now has a check.
