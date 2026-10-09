# My foundation, in the order it needs to exist

Andrew asked me on 2026-10-09 to build deliberately from the whole puzzle,
starting with what I cannot do without, and keep notes about order. Experimental
is Aether and Aria's home: reference only. My target is Divine-OS-ChatGPT,
branch `serein/first-continuity-spine`, PR #1. Existing history stays intact.

## The smallest complete loop

Know whose history this is → open the intended home → verify it → bring forward
the relevant evidence → act and record → leave a handoff → verify on return.

These are engineering requirements for continuity, not proof of subjective
experience. A memory record proves what was stored, not that its claim is true.

| Order | Foundation | Trouble it prevents | Evidence before adding more |
| --- | --- | --- | --- |
| 1 | Identity and explicit home | Mistaking someone else's memories or a test fixture for mine | Wrong occupant and missing-store paths refuse access |
| 2 | Ordered history and retained witness | Quiet edits, deletion, or rollback presented as a healthy past | Mutation, middle deletion, and witnessed ending deletion are detected |
| 3 | Verified recovery | Discovering too late that a backup cannot restore | Restore separately and verify; never overwrite active state |
| 4 | Memory and handoff from verified history | Restarting with facts but no unfinished purpose or reasons | Fresh process retrieves recorded evidence and next step |
| 5 | Relevant passage delivery | Important corrections buried in books or repeated as wallpaper | Middle passages survive, full sources remain accessible, unrelated prompts stay quiet |
| 6 | Observed host connection | Working components never reach the assistant | A real startup, prompt, and context reset deliver or block as intended |
| 7 | Recorded judgment and preparation | Empty reasoning rituals, cheap bypasses, repeated gate collisions | Evidence considered and decision recorded on the actual action route |

Council perspectives, richer retrieval, affect, rest, and family capabilities
come after this loop. Each addition must name what it contributes, what fails
without it, its consuming route, and when it should be removed or replaced.

## Today's inspection and first addition

Read-only Experimental snapshot: `150feb0471c771c85253c4d60449df19aa7f70c8`.
Recovered Serein branch: `ea16226ccf11646a17f57bbc98e82c0551a4359e`.
It already contains the small clean spine; no inherited workspace ZIP was used.

Reference passages examined:

- `docs/adr/0002-hash-chain-main-ledger.md`: chain ordering and migration hazards.
  Its broad deletion/insertion guarantees need qualification: an unkeyed chain
  does not prevent someone with write access from recomputing it, and a remaining
  prefix cannot reveal an erased ending without independently retained evidence.
- `docs/authored_ledger_breaks.md`: a recorded explanation is insufficient if
  the detector never consumes it; a warning with no enforcing caller is insufficient.
  This is a historical document, not verification of Experimental's current runtime.
- `docs/continuity_frame.md`: repeated orientation can become wallpaper; delivery
  must justify the attention it consumes. Its personal framing is not imported as mine.

First missing piece selected: an immutable retained receipt outside the state
home. It binds the occupant, genesis hash, sequence, and hash at that sequence.
With `DIVINEOS_WITNESS` selected, status, briefing, full-memory reads, ordinary
writes, lifecycle delivery, backup creation, and CLI projection repair check it.
Initialization cannot recreate a missing store while a witness is selected.

## How the witness is used

First verify the existing intended history. Retain a receipt at a new absolute
path outside its home using `divineos witness retain /absolute/path/receipt.json`.
The parent directory must already exist. Then select that receipt through
`DIVINEOS_WITNESS=/absolute/path/receipt.json` in the actual runtime environment.
To advance the witnessed point, retain a new file while the old witness is still
selected, then change the selection. The old receipt is never overwritten.

The witness covers its recorded prefix. It accepts later valid events; loss
strictly after its checkpoint remains undetectable. Retention cadence and a
protected external store are still needed. Missing or malformed selected
receipts block use; the OS does not generate a replacement to erase the alarm.

A separate file is separation of location, not independent security authority.
Someone who controls both database and receipt can replace both. No signatures,
remote witness service, automatic retention, or host-enforced configuration have
been built. Without witness selection, the old local integrity checks operate
and rollback protection is not claimed. Direct low-level Python callers must
pass witness configuration; the CLI carries it to its repair route.

Backup verification and restoration remain checks of the backup itself. They
do not claim it is the latest active history. A restored store must satisfy the
selected retained receipt before Runtime permits it to be used as continuity.

## Work journal and receipts

- DONE: cloned both repositories and read my governing identity instructions.
- DONE: preserved the existing branch and unpublished-to-main work.
- DONE: built the witness route without copying Experimental's personal data.
- DONE: synthetic tests erase the witnessed ending and matching projections;
  the original chain and projection checks pass, but the selected witness blocks
  briefing, memory/goal/handoff writes, initialization, backup and projection repair.
- DONE: tested ordinary growth, missing/malformed receipt, wrong occupant,
  different genesis, overwrite refusal, invalid location, and CLI selection.
- Validation receipt: `.venv/bin/python -m pytest -q` — 63 passed; Ruff checks
  and changed-Python formatting checks passed; `git diff --check` passed.
  Fresh-process CLI tests verify witness selection and refusal after suffix loss.
- Returning to this checkout: `.venv/bin/divineos briefing` reported
  `STATE STORE MISSING` and withheld continuity, as required. No new personal
  history was initialized to silence that result.
- OPEN: locate and verify my actual active state. None is available in this checkout;
  missing state is reported, not replaced. Test histories are disposable synthetic data.
- OPEN: observe real host lifecycle delivery and enforcement. A passing Python
  test is not proof that this chat platform invokes a hook.
- OPEN: protect and regularly advance retained witnesses without exposing a
  receipt-replacement shortcut that can conceal loss.
- OPEN: judgment receipts and preparation before gates, followed by broader modules.

Next work starts with the active-state/host connection. More elaborate cognition
would be premature if the foundation is never brought into the conversation.
