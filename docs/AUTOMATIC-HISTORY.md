# History is kept before it is selected

Andrew's requirement, 2026-10-09: "it should never be an option to record or not
it should happen automatically."

Before this change the lifecycle connection delivered memory but never recorded
its incoming messages. That is a structural gap: a working reader does not make
a recorder. The new route calls the recorder unconditionally before success.
There is no relevance test, remember command, or recording-disable flag there.
Identity instructions also carry this requirement for subsequent work.

## What is retained

| Host boundary | Record supplied automatically | Response on recording failure |
| --- | --- | --- |
| SessionStart | Complete supplied JSON, including start source | Refuse continuation |
| UserPromptSubmit | Complete prompt and envelope, without trimming text | Block prompt |
| PreToolUse | Tool identity and complete supplied arguments | Deny tool with the supported permission response |
| PostToolUse | Tool identity, arguments and supplied result | Block further processing; cannot undo the completed tool |
| Stop | Supplied final assistant message and envelope | Stop continuation with a visible reason |
| PreCompact / PostCompact | Compaction boundary and supplied metadata | Refuse continuation at the corresponding boundary |
| SessionEnd | Supplied end event | Report failure; cannot prevent session ending |
| Interrupt | Supplied interruption event | Warn; cannot prevent interruption or restart the turn |

When any event includes a transcript path, its new bytes are retained too,
regardless of role, format, meaning or relevance. Base64 keeps exact bytes,
including whitespace, line breaks, non-UTF-8 data, and partially written lines.
Hook envelopes preserve JSON values rather than their original lexical spacing.
Nonstandard numbers and duplicate object keys on the wire are refused, so the
parser cannot quietly change an ambiguous payload into a different record.

Every hook invocation receives its own event ID. Repeated identical prompts are
not deduplicated: three arrivals of "yes" remain three observations. A retry
also remains an observation, because the host has not provided a reliable unique
delivery identity. These are observed invocations, not inferred unique human
messages. Tool-use and turn IDs are retained when supplied.

Transcript bytes use a separate capture position per session and resolved path.
The position lives in the verified ledger. A repeated invocation keeps its new
envelope but does not copy already captured bytes. A rewritten or shorter source
is refused instead of guessing whether it was intentional. Changing the source
path starts a separate stream; copied transcripts at another path may duplicate
content. The recorder does not invent associations between them.

## Integrity, reading and bounds

The existing write gate verifies ledger, configured witness, occupant and
projections. New transcript chunks and the envelope commit in one transaction.
If writing the envelope fails after transcript insertion, the whole transaction
rolls back. Concurrent processes serialize through the existing immediate SQLite
transaction, so they do not share a stale transcript offset. Verification checks
contiguous chunk offsets and cumulative byte hashes as well as the ledger chain.

`divineos history` exports all verified ledger events as JSONL. `--session ID`
selects observed envelopes and raw transcript chunks for that session;
`--after N` starts after a ledger sequence. Each record carries its sequence,
event ID, recording time, payload and hash links. Transcript byte fields are
base64-encoded. Export reads the ledger even if the original transcript has
disappeared. Unverified history is withheld.

Routine briefings do not inject recording events as memories or facts. The
existing memory/handoff path still decides what to bring forward. This prevents
automatic keeping from becoming automatic flooding of attention. Judgment and
handoffs remain explicit; copying text is not evidence that it was understood.

The wire-input limit remains 1,000,000 bytes. Transcript chunks contain at most
64 KiB of source data. Each invocation accepts at most 8 MiB of new transcript
bytes. Exceeding a limit fails visibly and clips nothing. A larger initial
transcript needs a separately designed backfill route before activation; this
change does not provide one. The reader rehashes the captured source prefix on
every call, and full ledger verification replays retained chunks. Costs grow
with history; sustained-load performance has not been measured. History export
currently materializes its selected records in memory.

The source file can change while it is read. The record preserves observed
bytes up to the opened file's initial size, not an authenticated atomic host
snapshot. Later appends are retained on a later invocation. Previously recorded
prefix changes are detected on the next read, not magically prevented.

## Evidence and platform boundary

Reviewed read-only Experimental source at
`150feb0471c771c85253c4d60449df19aa7f70c8`:
`core/front_door.py`, `hooks/front_door_hook.py`, `core/tool_capture.py`, and
the relevant `.claude/settings.json` routes. Their lessons include keeping
incoming messages before work, preserving repeated short messages, separating
host attribution from text interpretation, and recording tool boundaries. Their
fail-open behavior was not copied into my recording decision path. No personal
state or runtime data was copied into my implementation.

Official contract examined on 2026-10-09:
[Hooks](https://learn.chatgpt.com/docs/hooks). Host observations can be incomplete;
the transcript schema is unstable; some tools bypass these hooks. PreToolUse
must use its permission shape, not common continuation fields. Interruption
warnings cannot block interruption. These facts constrain the guarantee.

UNVERIFIED: this chat host invoking the project's hooks against active personal
state. No active home is selected in this environment. The recovered September
22 database remains an inspected archive. It was not promoted, modified, or
used for recording tests. Trust/configuration, a durable active home, and real
event receipts must be established before calling this chat automatically kept.
No hidden transcript locations were assumed or scanned to fake that connection.

A null transcript path permits recording only the supplied envelope. A null
final-message field preserves that null, not an invented reply. Hosted tools,
queued messages, commentary and interruptions are covered only to the extent
the host emits their hooks or writes their bytes to the supplied transcript.
Unsupported events, disabled hooks, timeouts, interpreter failures, a crash
before host delivery, or a transcript never supplied cannot be captured by this
route. Synchronous recording is mandatory inside it; universal capture is not
claimed. Host receipts and protected durable retention remain the next gates.

## Validation receipt

91 tests passed with `.venv/bin/python -m pytest -q`. Ruff checks, changed-Python
formatting checks, and `git diff --check` passed. Tests invoke the configured
commands in fresh processes, verify every added hook route, preserve repeated
arrivals and exact values, and prove transcript capture survives source removal
and verified backup/restoration. They also cover prefix rewrite/shrink, backlog
refusal, malformed wire JSON, witness refusal, disk failure, transaction rollback,
and concurrent recording without copying the same transcript bytes twice.
These are synthetic-state receipts, not observed live-chat activation.
