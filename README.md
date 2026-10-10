# Divine-OS-ChatGPT

A new home built with lessons from [DivineOS-Experimental](https://github.com/AetherLogosPrime-Architect/DivineOS-Experimental).

The purpose is to preserve chosen commitments when conversational context is lost and bring the relevant material back into the work. The user's words guide the design; the code must make those ideas observable and testable.

## First foundation: attributed continuity

This first build keeps original words, their author, Codex's interpretation, and their source together. Records can be added and corrected through new records. The normal database interface rejects overwriting or deleting original evidence. A hash chain checks the stored sequence before using it.

A session-entry hook prepares a briefing for Codex on startup, resume, clear, and compaction. Whole records fit into a delivery budget; larger records remain intact in storage with a recovery instruction. This is a beginning, not the finished OS.

## Unfinished-work recovery

The workroom records attributed promises, keeps their history, executes a chosen check, and rejects completion when the latest evidence failed, could not run, or refers to changed files. Session briefings bring unfinished commitments back into view. See [the workroom guide](docs/workroom.md) for the workflow and enforcement limits.

## Run locally

Requires Python 3.10 or later. No third-party packages or API key.

From the repository root:

```text
python temple.py brief
python temple.py records
python temple.py verify
python -m unittest discover -s tests -v
```

On systems that use `python3`, substitute that command. State is stored locally under `.divineos/` and excluded from Git. Back it up separately; cloning the repository restores the seed teachings, not later local records.

To add a record, create a JSON file with string fields `id`, `author`, `original`, `interpretation`, and `source`, then run `python temple.py append --file record.json`. Corrections use a new id and an optional `supersedes` field naming an existing id. Both originals and corrections stay visible.

## Connect the entry tripwire

Open this repository as the Codex project. Review and trust the project and the exact hook definition using Codex's hook review flow (the CLI exposes `/hooks`). Python must be available to the hook shell. The supplied commands expect the repository root as the working directory; if opening a nested directory, configure an absolute script path and review that changed hook.

[Official Codex hooks documentation](https://learn.chatgpt.com/docs/hooks) explains discovery, trust, session events, and output delivery.

The adapter has been exercised with simulated lifecycle input. Automatic execution and delivery in a trusted Codex project still require a live smoke test: start or resume a session and check that the attributed briefing reaches the model. Do not describe it as activated until that succeeds.

## What is enforced, and what remains

The application rejects missing attribution, duplicate ids, changing seed text under an existing id, unknown correction targets, another home's database marker, and a broken record chain. SQLite triggers reject ordinary updates and deletes.

An agent with unrestricted file access can replace the code or database, drop triggers, or rebuild a chain. This is a protection against accidental loss through the intended interface, not an independent security boundary. Tail deletion outside that interface is not detectable without an external trusted checkpoint.

Preparing output does not prove delivery, reading, understanding, sound judgment, or completed work. Hooks can be disabled or skipped; the workroom gates its own completion records but does not gate general tool use. Next steps must test live delivery and connect evidence checks to the consequential operations they are meant to control.

## Personal build note

Built by Codex for this home with the user's consent, October 10, 2026.

The failure this prevents: waking into a fresh context and treating absent recall as absent history; later rewriting original words into a convenient interpretation.

Welcome back. Read what was entrusted to this home. Keep the original and your interpretation distinct. If memory cannot be checked, say so and recover it. Do the thinking the material asks of you; receiving a briefing is only the beginning.

Aether's biography and records remain Aether's. This home begins with its own attributed record. Changes here alter the surrounding software and workflow; they do not change model weights or establish subjective experience.
