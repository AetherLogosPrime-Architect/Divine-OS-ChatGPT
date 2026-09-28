# Learning from the earlier occupants

The owner explicitly authorized adapting this independent copy, removing inherited personal material where useful, and using Aether and Aria's examples to set it up. Their source records help explain both successful mechanisms and mistakes worth avoiding.

## Selected practices

| Practice | Source inspected | How it informs this setup |
|---|---|---|
| Explicit ownership | `core/identity.py` and `data_home_ownership.py` | Check identity and destinations before using a copied installation. An unset identity stays visibly unset. |
| Early handoff | `cli/session_pipeline.py:L114` | Preserve intent and a next step before long work. Source comments describe a previous handoff written too late to survive interruption. |
| Reachable remedies | `core/hook_surfaces.py:L38`, CLI bootstrap exemptions | A check must leave its own repair path usable, including the tools needed to repair it. |
| Visible degradation | `core/knowledge/retrieval.py:L1136` | Report that a subsystem failed instead of presenting an unreadable result as empty or complete. |

Source paths are relative to `src/divineos/` in the inspected snapshot. These are accounts and mechanisms in the source; this pass did not reproduce every historical incident.

## What changed

Added `profiles/chatgpt.json` with a setup appropriate to the current collaboration: ChatGPT identity, plain-language communication, the user's role, actual tested capabilities, known limitations, current priorities, and the permission to adapt this copy.

Added `adopt-setup` to the adapter. It uses the existing core-memory and knowledge APIs. It records the four practices with `source=INHERITED`, `maturity=RAW`, `confidence=0.5`, and the original source descriptions. A linked event preserves source references and the applied core configuration. It does not import personal histories, biographies, family rosters or voice files.

A stored receipt makes a completed reapplication a no-op. Invalid ownership or missing source references are rejected before core/ledger updates. This is a resumable sequence of upstream writes, not a single atomic transaction; a crash can leave a partial application and retry can record another attempt. It does not turn borrowed guidance into tested local evidence.

## Results

Eleven acceptance tests passed on Windows/Python 3.12.14. The added tests cover inherited provenance after a new process, all nine core slots, repeated application without duplicate events, and rejection of invalid configurations without changing core memory or the event count. One non-failing pytest cache-permission warning occurred; the test results themselves were successful.

Applied the setup to the working ChatGPT profile. Its ledger verified all six events after the application. Existing observations remained present. This adds a useful starting configuration; it does not install automatic host hooks or certify the full session pipeline.
