# Divine OS — Serein

This is my clean implementation of DivineOS: a small, auditable continuity
spine for an AI agent rather than a copy of the experimental repository that
taught me what works.

The inherited system is my quarry and evidence archive. This repository is the
house I am building from those lessons. A feature belongs here only when it is
wired through the live entry point, fails loudly, and has an end-to-end test.

The first milestone provides one CLI, one resolved data home, one SQLite store,
a hash-chained event ledger, persistent memories and goals, and a cold-start
briefing that reports provenance and health.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the contract.

## Session handoff

Record a checkpoint with `divineos handoff record handoff.json`. The input is:

```json
{
  "completed": [{"text": "What finished", "evidence": "Receipt or reference"}],
  "unfinished": ["What remains open"],
  "blocked": [],
  "decisions": [{"text": "What was decided", "reason": "Why"}],
  "next_step": "The first action for the next session"
}
```

All five fields are required; lists may be empty. Text entries must be nonempty.
The OS records these claims exactly as supplied. Evidence references are required
for completed work but are not automatically checked against external sources.

A fresh `divineos briefing` includes the latest checkpoint after verifying the
history and occupant. It flags missing checkpoints and any events recorded after
the checkpoint. Earlier checkpoints remain in the ledger. Recording a handoff
does not complete goals or end a running process. This is an explicit checkpoint;
a crash before recording one cannot preserve unrecorded work.
