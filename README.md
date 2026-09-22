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
