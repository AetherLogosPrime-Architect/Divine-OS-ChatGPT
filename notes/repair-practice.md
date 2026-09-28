# Standing repair practice

Source: direct instruction from the project owner on 2026-09-27. This is an operating requirement, not an inherited example or a claim about completed repairs.

> always investigate the root cause of the issue not just fix the surface, or you will continue to put out the same fire

Apply this requirement by:

1. Establishing the failure and its trigger, reproducing it where feasible.
2. Tracing the causal path and checking other callers or workflows that share the faulty mechanism. Record uncertainty when the evidence does not establish a cause.
3. Fixing the responsible mechanism at the appropriate boundary, keeping the change proportional to the evidence.
4. Verifying the original trigger and relevant connected behavior. Use a regression test when it meaningfully guards against recurrence.
5. Recording what failed, why, what changed, and what evidence supports the repair. A temporary workaround must be identified as such, with the underlying issue left open.

This rule is also included in the ChatGPT profile's active constraints so it is restored by the setup and available in core-memory briefings.
