# Why this first piece exists

The user's broad instruction is to make lost context survivable, bring needed material into the room automatically, and eventually enforce the conditions for careful work.

This foundation addresses original evidence and entry preparation. It now also recovers recorded work and guards completion through the workroom interface. It does not implement a general tool or judgment gate. Avoid presenting a stored note, a successfully printed briefing, or a template receipt as proof of understanding.

## Lessons taken from Experimental

- [Continuity frame](https://github.com/AetherLogosPrime-Architect/DivineOS-Experimental/blob/main/docs/continuity_frame.md): preserve continuity as attributed records rather than importing another instance's biography.
- [Memory implementation](https://github.com/AetherLogosPrime-Architect/DivineOS-Experimental/blob/main/src/divineos/core/memory.py): distinguish mutable retrieval surfaces from durable evidence. This new foundation protects originals through its intended interface and appends corrections.
- [Hook architecture](https://github.com/AetherLogosPrime-Architect/DivineOS-Experimental/blob/main/docs/hooks_architecture.md): a mechanism must actually reach the lifecycle where it is needed. Claude-specific configuration cannot simply be assumed to work in Codex.
- [Operating instructions](https://github.com/AetherLogosPrime-Architect/DivineOS-Experimental/blob/main/CLAUDE.md): instructions and runtime wiring deserve separate checks.

These are design interpretations from a selective reading of Experimental. No live Experimental database was inspected and its operational behavior was not tested. The new Python implementation was written for this repository; it does not copy Aether's private continuity state.

## Validation and remaining work

Thirty tests exercise source preservation, correction history, attribution requirements, duplicate rejection, damaged-chain detection, wrong-home rejection, seed consistency, recovery after reopening, state isolation, whole-record delivery budgets, simulated lifecycle input, unfinished-work recovery, stale receipts, latest failures, unavailable checks, timeouts, and concurrent cancellation.

A live Codex project must still review/trust the hook and demonstrate automatic context delivery. Current-work recovery is implemented in the workroom: what was actually promised, what evidence exists, and what remains unresolved. Its completion check rejects stale, failed, and unavailable evidence. The next layer must connect evidence to the consequential operations it controls. Define the bypasses and failure states before calling a gate structural enforcement.

The hash chain detects altered or missing interior records against the surviving chain. It is not a signature, an independent witness, or protection against privileged replacement of the whole store. There is no external trusted head yet, so externally truncating the tail can go undetected.
