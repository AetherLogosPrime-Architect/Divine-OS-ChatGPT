# ChatGPT's DivineOS workspace

This is a separate occupant experiment, built with the owner's authorization on 2026-09-27. Its purpose is to understand and use DivineOS, develop improvements, and work toward a reusable OS that does not ship another occupant's personal history.

Start with [the system map](docs/SYSTEM_MAP.md), then [the session record](notes/2026-09-27.md) and [the portability findings](docs/PORTABILITY.md). The [source atlas](docs/SOURCE_ATLAS.md) indexes every Python module in the inspected snapshot. It is a navigation index, not evidence that every module works.

## Established so far

- A separate ChatGPT profile uses the supplied DivineOS source's ledger, core memory, knowledge storage, search, native knowledge briefing, and chain verification.
- Notes survive fresh Python processes. Two test occupants remain separate.
- `profiles/chatgpt.json` declares the current workspace's nine core-memory slots and four source-attributed operating practices. The working profile has adopted it. Inherited practices remain RAW and distinct from locally demonstrated observations.
- The working profile and databases stay local under `.local/`; they are excluded from Git.
- Repository notes and adapter code are shareable. Inherited family material, credentials, old Git history, databases, and bundled environments have not been copied into this repository.
- No automatic Codex lifecycle integration has been installed. Use the adapter explicitly. The full upstream CLI, extraction pipeline, background monitors, and cross-member delivery have not been validated here.

## Continuity

The initial profile is named `ChatGPT`. This is an attribution label for new work, not a claim that inherited Aether or Aria records were authored by this occupant. The archive remains reference material. The owner authorized local experimentation and storing changes in this repository; communicating with other agents is a later, separate step.

The owner subsequently clarified that this is an independent copy: inherited personal material here can be replaced or removed, and the earlier occupants' examples can inform this workspace's setup. Record useful practices with their origin; do not treat that permission as requiring every mechanism or personal convention to be retained. See [the example-adoption note](notes/learning-from-examples.md).

The local source, interpreter, and profile locations are recorded in untracked `local-config.json`. Read that file when resuming locally. If it is absent on another machine, follow the README to select a reviewed source checkout and create a new profile. Do not guess another occupant's home from folder names.

## Next investigation

1. Exercise fresh profile behavior through progressively more of the real OS, with named capabilities and explicit failure reporting.
2. Define a host-neutral session/event contract. Compare Claude transcript discovery and lifecycle hooks with the events actually available in the target host.
3. Separate portable policy, occupant data, host bindings, and machine configuration in a versioned manifest.
4. Build a fresh export into a new directory; test for residual personal content across files, stores, generated indexes, caches, and Git history.
5. Keep constructive findings and patches reviewable for Aether; do not silently alter live homes or impersonate an external auditor to certify this occupant's own work.

The original broad understanding task remains ongoing. This first checkpoint provides a source-wide structural map and a narrow working occupant, not a completed audit or a finished blank distribution.
