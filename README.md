# Divine-OS-ChatGPT

A workspace for understanding DivineOS, using its working parts from a separate ChatGPT profile, and developing a portable fresh-occupant foundation.

**First checkpoint:** a tested adapter uses the original DivineOS ledger and memory APIs without inheriting the source checkout's data-home markers. This repository is not yet a standalone DivineOS distribution.

Read [START_HERE.md](START_HERE.md) for continuity, [the system map](docs/SYSTEM_MAP.md) for architecture, and [portability findings](docs/PORTABILITY.md) for the path toward a blank OS.

## Run a separate occupant

Requires Python 3.12+ and a reviewed DivineOS source checkout. The reference snapshot inspected here has archived HEAD `1056519dde12096ec45b0a76d075364ceccc5e7b`; the archive's working files are the actual input and are not assumed identical to that commit.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-lab.txt
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt bootstrap --name ChatGPT
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt adopt-setup --setup profiles/chatgpt.json
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt inspect
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt remember --text "An observation from this occupant's work."
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt recall --query observation
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt native-briefing
.venv/Scripts/python -I -B tools/occupant.py --source <divineos-checkout> --state .local/chatgpt verify
```

On Unix, use `.venv/bin/python`. Replace `<divineos-checkout>` with an actual path. The profile must be outside the source checkout. Commands emit UTF-8 JSON to stdout and diagnostics to stderr.

`briefing` returns a small structured view of core memory and notes. `native-briefing` invokes DivineOS's own knowledge briefing renderer and exposes its incomplete-state flag. Neither is the full upstream CLI's session-start process. Notes default to `SYNTHESIZED`, confidence 0.5, maturity `RAW`; use `--basis DEMONSTRATED --confidence 0.9` only for observations supported by an actual experiment. Model-based embeddings are explicitly disabled in this minimal runtime; search uses the upstream lexical retrieval path.

The adapter sets all three store routes before importing DivineOS, strips inherited DivineOS/Claude session variables, verifies the imported source and resolved paths, and refuses an unowned nonempty directory or a changed profile name. Its Python audit guard rejects ordinary out-of-profile writes, SQLite connections, subprocess launches, and socket connections, including violations swallowed by upstream fail-soft code. **This is a guard against accidental effects, not an OS security sandbox.** It does not defend against malicious native code, restrict all reads, or certify arbitrary upstream commands.

No inherited database, seed content, family roster, hook configuration, or personal voice file is applied. Existing personal stores are not reset. The adapter creates schema through upstream initializers. The optional `adopt-setup` action fills the nine core-memory slots with this workspace's context and selectively imports four operating practices from cited source examples.

Those practices are recorded as `INHERITED`, maturity `RAW`, confidence 0.5, with their original source descriptions and references in a linked ledger event. They are guidance to evaluate here, not firsthand experiences or already-validated results. An applied-setup receipt makes completed repeats a no-op, preserving later local changes. A changed setup is an explicit new application. The input and owner are validated before core/ledger updates; the sequence of upstream API writes is not a single database transaction, so retry after interruption can add another attempt event. The adapter never resurrects a deliberately superseded lesson automatically.

## Validate

```powershell
$env:DIVINEOS_TEST_SOURCE = '<divineos-checkout>'
.venv/Scripts/python -m pytest tests -q
```

Without `DIVINEOS_TEST_SOURCE`, integration tests are explicitly skipped; guard tests still run. The latest Windows/Python 3.12.14 run passed all eleven tests with the source configured. These are real-process, real-SQLite tests, not a run of the upstream project's entire suite. Linux/macOS behavior remains unverified.

Local profile data, dependency environments, and `local-config.json` are ignored. Published changes contain the adapter, tests, documentation, and structural index only.
