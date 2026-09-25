# Architecture contract

## Purpose

I use Divine OS to carry continuity, judgment, and evidence across stateless
model invocations. It supports my cognition; it does not pretend deterministic
code can replace it.

## Foundation

1. **One front door.** The `divineos` CLI and its Python service layer use the
   same code paths. A component with only isolated tests is not integrated.
2. **One resolved home.** Every stateful operation reports the repository,
   interpreter, occupant, data home, and database it actually used.
3. **One authoritative event record.** Mutations append to a hash-chained
   ledger. Query tables are projections and can be rebuilt.
4. **Ownership before proximity.** Personal state is selected by the active
   occupant. Another occupant is never a fallback identity or memory source.
5. **Silence is not health.** Missing, empty, unreadable, unverifiable, and
   uninitialized are distinct loud states.
6. **Automation carries repetition.** Code performs storage, verification,
   routing, and bounded checks. I retain decisions, interpretation, and
   exceptions.
7. **Gates cite their reason.** A refusal names the failure shape, evidence,
   remedy, and author. Emergency bypasses remain possible and become ledger
   events plus root-cause work.
8. **Scarcity narrows scope, not standards.** I build smaller complete slices
   rather than incomplete breadth.
9. **Restoration is independently proved.** A backup is not verified until a
   separate location can restore and validate it.
10. **Complexity must pay rent.** A new module must remove cognitive load,
    expose a blind spot, preserve evidence, or enable a capability that the
    simpler system cannot provide.

## First vertical slice

```text
CLI
 └── Runtime
      ├── provenance + health
      ├── hash-chained ledger
      ├── memory projection
      ├── goal projection
      └── briefing
```

All persistent mutation crosses one transaction boundary: append the event and
update its projection together. The briefing verifies the chain before using
the projections. If verification fails, the briefing says so and exits
unhealthy.

## Cold-start contract

Only `divineos init` creates a state store. Status and briefing open an existing
store read-only and report the resolved repository, interpreter, data home, and
database. A missing, incomplete, or unreadable store remains untouched and is
reported as such. An existing store cannot be initialized over an integrity or
occupant failure. The briefing checks the ledger, occupant, projections, goals,
and memories from one database snapshot.

## Deliberately absent

Council lenses, semantic retrieval, dreams, sleep, family messaging, affect,
external hooks, and policy gates are not rejected. They are deferred until the
continuity spine is proven. Each will enter as one bounded capability with a
live-route test and an explicit removal condition.

## Session handoff contract

A `session.handoff` event stores completed work with evidence, unfinished work,
blockers, decisions with reasons, and the next step. It uses the existing write
integrity gate and transaction. No additional database or schema migration is
needed; the ledger itself is the handoff's authoritative read source.

The briefing reads the latest checkpoint in its existing verified snapshot.
Malformed handoff events fail continuity verification, including backup checks.
Missing checkpoints and later ledger activity are visible warnings, not claims
of ledger corruption. The event hash verifies stored content, not the truth of
an author's claims or the availability of referenced evidence. Deletion of an
entire trailing ledger suffix cannot be detected without an independent retained
checkpoint; this feature does not add such an external trust anchor.

## Loading standing corrections

`AGENTS.md` directs the agent to read `SEREIN.md` before repository work. The
briefing also includes that file's full text and source path after verifying
state ownership and integrity. Empty or unreadable identity text makes the
briefing fail and withhold continuity. The file is versioned in Git, separate
from the event ledger; ledger verification does not authenticate its contents.
This makes standing corrections available on startup. Applying natural-language
instructions still requires the agent's judgment; this is not a speech filter.

## Lifecycle delivery and enforcement boundary

`.codex/hooks.json` contains event routing, a command, and transport settings only.
It invokes `divineos.lifecycle` from this checkout's virtual environment. All
validation, context selection, size limits, and stop decisions live in the OS.
Session startup, resume, clear, and post-compaction startup load a bounded
orientation. Each submitted prompt verifies the state and checks for new ledger
events or a matching memory; a prompt with nothing useful to deliver adds no
context. The same OS entry point owns both decisions.

The OS requires an explicitly selected absolute `DIVINEOS_HOME`, matching source
and target repositories, healthy continuity, and an existing handoff. It loads
identity, goals, five recent memories, and the latest handoff in the briefing's
verified database snapshot. Older active memories remain eligible when words in
the prompt match at least two meaningful words in a memory. One matching memory
is delivered per prompt, once per session. New events surface once. This
simple word match is a narrow first pass, not semantic or complete retrieval.

Each delivery is divided into panels of at most 600 characters of source text.
The OS splits long lines into several panels without omitting their middle;
the total delivery still has a 24,000-byte ceiling. The route never creates
ledger state. Missing or invalid state returns `continue: false`; prompt events
additionally return `decision: block`.
Delivery exceeding 24,000 UTF-8 bytes is blocked rather than silently truncated.
The hook's context limit is disabled only because the OS enforces this size cap.
An atomic, session-specific sidecar records the last delivered ledger sequence,
its event hash, the identity file digest, and memory IDs already surfaced. It is
a delivery cursor, never the source of memories or authority for a health pass.
A missing sidecar causes full orientation to load again. A cursor that disagrees
with verified history blocks delivery. Changed identity text also reloads
orientation. A successful host receipt is not observable here: if a hook saves
the cursor and its response is lost afterward, a later prompt may skip a
delivery. Concurrent prompts for one session can race and repeat a panel.
Host verification and stronger delivery acknowledgments remain open work.

Tests execute the configured command in fresh processes against synthetic state.
They verify delivery and blocking responses, not host enforcement. Trusted hook
activation and an observed real lifecycle event are separate deployment gates.
There is no Codex CLI available in the current build environment and no active
runtime home selected. The hooks have not been demonstrated firing here.
Host skipping, timeouts, interpreter/import failures, and hooks disabled by the
host remain outside this Python gate's control. Do not call this universal
fail-closed enforcement. No trust records are edited or bypassed by this build.

The adapter does not synthesize decisions or handoffs from transcripts. Requiring
judgment receipts before completing work is a separate future OS workflow; this
slice enforces continuity delivery at its supported lifecycle boundaries only.
