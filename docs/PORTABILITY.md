# Toward a fresh-occupant DivineOS

The owner's goal is to preserve the working systems while removing personal state for a new agent. Aether and Aria keep their existing homes. This pass uses a new profile rather than deleting anything from theirs.

## Observed boundaries

### A folder copy is not a new home

The supplied `.divineos_data_home` and `.divineos_canonical` markers still point outside the archive's folder, into the original occupant's user-home store. Environment overrides take precedence in `core/paths.py`, `_ledger_base.py` and `family/db.py`, but a caller must set them before imports with side effects. `ledger.py` creates log files at import time.

**Implemented here:** explicit source and state arguments; all three store routes set before imports; clean per-process user/temp/cache directories; source/path verification; refusal to take over an existing unowned directory; and a Python-level accidental-write guard. Local state never enters the public repository.

### Reset is not yet a complete personal-state export boundary

`cli/admin_reset_template.py` uses `_LEDGER_TABLES_TO_CLEAR` (L174), `_FAMILY_TABLES_TO_CLEAR` and `_FTS_TABLES`, passed into `_clear_db_tables` (L293) at L510–511. The `bio` table defined in `core/bio.py:L38` is not on those lists.

**Synthetic reproduction:** execute the unmodified clear helper extracted from its AST, with its original lists, against a disposable SQLite fixture containing one event and one biography. The event row is removed; the biography remains. This verifies the helper/list omission. The full destructive CLI was not run against a live or archived store. The remainder of the command was inspected: it clears selected directories, re-seeds, rebuilds FTS, and refreshes active memory; it does not explicitly clear `bio`.

There are further static omission candidates, but a broad SQL-text scan includes false positives and dynamic schemas. Those candidates are not counted as confirmed defects. Separately, removing a few directories would not remove personal records from Git history, generated graphs, backups, dreams, or other undeclared state locations.

**Design direction:** construct a new distribution from an explicit component manifest and initialize fresh stores. Keep any personal-data migration opt-in and separately attributed. If reset-in-place remains supported, give every persisted component an explicit reset/retain policy and make an unknown component block a claim of complete erasure.

### Identity remains embedded in some defaults

`core/identity.py` has an explicit unset/unreadable distinction and avoids silently defaulting to Aether. In contrast, `core/bio.py` still defaults both its schema author and `bio_write` author argument to `aether` (L44/L55 in this snapshot). This is a source-level portability observation, not a report that this adapter mislabeled a biography—it does not currently invoke that API.

The seed's identity and relationship slots already use placeholders, which is useful groundwork. Personal assumptions also appear outside the seed in startup text, policy, defaults, family material, and host integration. Clearing the seed alone cannot establish neutrality.

### Host events are a separate integration layer

The configured Claude hook counts are: SessionStart 1, UserPromptSubmit 1, PreCompact 1, PostCompact 1, PreToolUse 30, PostToolUse 16, Stop 14. A router registration can itself dispatch multiple surfaces, so these are command registrations rather than a total mechanism count.

The full extraction pipeline starts by discovering host session transcripts. A portable API needs explicit events and transcript provenance rather than assuming a Claude directory layout. No automatic Codex hook installation is claimed here.

### Fresh schemas need a declared capability set

The first minimal profile had ledger, core-memory and knowledge tables. Native briefing worked partially and explicitly reported missing `knowledge_edges` and `open_questions`. The adapter now initializes those through existing upstream functions. The tested briefing then completed without its incomplete warning.

This suggests capability-driven initialization: each enabled feature declares stores, dependencies, migrations, host events and read/write roots. A health report should distinguish absent-by-design, unavailable, failed, and working. A generic success-shaped message is insufficient.

## Build sequence

1. **Working foothold — implemented:** separate profile, identity attribution, note/recall, native knowledge briefing, provenance paths, chain verification, and eight tests.
2. **Host adapter — not implemented:** explicit session-start, user-input, tool-result, pre-compaction and handoff contract with reproducible fixtures.
3. **Component manifest — design stage:** portable code, reusable policy, optional example material, personal state, host bindings, machine secrets/configuration.
4. **Fresh exporter — not implemented:** create a new directory and new Git history from allowed components; never erase the source home to prepare an export.
5. **Acceptance suite — partial:** two occupants and process restarts tested. Still needed: interruption/recovery, corrupted stores, concurrency, optional-model absence, complete residue scans, OS portability and behavior-level longitudinal evidence.

No blank-release readiness claim is warranted yet. The adapter demonstrates a useful subset on a different host; it is not a replacement for the full OS.

