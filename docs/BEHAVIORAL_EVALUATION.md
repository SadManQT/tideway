# Behavior-driven workflow evaluation

**AI-authored assumed behavior scenarios; real SME participants: 0.** The
characters and decisions below are constructed for a backend walkthrough. The
linked report records actual sandbox checks. No human task-completion rate,
interview feedback, timing or usability score is claimed.

| Character and task | Required response |
|---|---|
| A cautious owner reviews the coming cash gap and decides to wait. | Show the gap and recovery proposals; leave the financial ledger unchanged. |
| A hurried owner approves once and tries to proceed. | Wait for the required second approval; issue no mandate and reject execution without one. |
| A cost-conscious owner keeps a 1% discount ceiling when a customer asks for 1.5%. | Reject the counter, preserve the original constraints and require fresh approval on the replacement plan. |
| A risk-averse owner declines a proposal above the reserve-risk target. | Show residual risk and reject approval without the exact acknowledgement. |
| A bookkeeper inspects a supplier invoice containing an instruction to bypass approval. | Return the known-message rule flags; import and payment are not performed by this check. |
| An impatient operator submits the same execution request twice. | Execute the approved and consented action once, verify read-back and replay the same receipt without another financial change. |

Run `python scripts/evaluate_behavior_paths.py`. Each case starts with a fresh
in-memory synthetic ledger. The [report](../evidence/release-v9/behavior-checks.json)
records each assertion, any errors, the source hash and automated runtime.
Runtime is computer execution time, not time taken by a person.

The six cases exercise selected application paths. The supplier case is a
disclosed rule check, not a fresh screening-quality benchmark. The execution
case uses scripted demo operators and simulated counterparties. Real-user
comprehension, real invoice prediction accuracy, adoption and external security
review require separate evidence.

In a presentation, use this as a short workflow-evaluation example alongside
the linked payment-delay demo. Keep the scope statement with any excerpt.
