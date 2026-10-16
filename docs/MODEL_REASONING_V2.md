# Guarded financial tool selection, runtime v2

This upgrade extends the existing optional TideLM architecture. It does not add
an approval, mandate, payment, SQL, shell, arbitrary URL or external-write tool.
The default assistant remains a labelled deterministic assistant. The animated
rescue workflow remains a deterministic orchestration; it is not relabelled as
language-model reasoning.

## What the optional model does

The first selection receives the user's original message plus scoped ledger
context: unique customer/supplier names, currency, major-unit convention,
current/target dates, horizon, role, autonomy and pause state. It returns a
public typed JSON selection. It never supplies financial outputs.

Scoped name lists exclude quarantined records and instruction-like names.
Follow-up model context uses a separate sanitised copy of observed results:
quarantined names are omitted, stored descriptions/messages/account fields are
removed, and remaining instruction-like strings become digest markers. Public
tool receipts and their hashes continue to describe what actually ran; they are
not rewritten to fabricate clean-looking evidence.

For ordinary forecast, risk, customer, credit or what-if requests, the selected
allow-listed tools calculate the answer and the multilingual deterministic
reply writer states their results. For a requested rescue, selected read tools
run first. Deterministic preflight supplies any missing likely forecast, seeded
risk simulation and security check. Those calls are explicitly labelled
`deterministic_rescue_preflight` in the trace.

If the likely reserve shortfall is zero and simulated breach probability is
below 15%, the guard returns `no_action_needed` without storing a rescue proposal
or making a second model call. Otherwise, the second model selection consumes
the actual observed tool results and original proposal constraints. It may
select a bounded proposal for human review. It cannot discard the original
exclusions, discount ceiling or preference. The planner decides feasibility;
`no_safe_plan` escalates without claiming that approval is available.

The public response contains `selections`, `trace`, `model_identity`,
`mode_label`, `model_iterations` and `decision_rationale`. Each executed tool
has a source label, permission, elapsed duration, full output hash and audit ID.
The brief rationale is composed from deterministic tool outputs. These are
observable selections and receipts, not hidden thoughts or an invented model
transcript. Result-aware tool selection is implemented; its performance with
the actual released model remains unverified on this machine.

## Validation and budgets

The whole selection passes contextual preflight before any proposal is stored.
That catches a valid proposal followed by an invalid customer rather than
partially applying the first call. Names must match exactly one ledger name,
ignoring case. Fuzzy guesses and ambiguous case variants require clarification.
Viewer proposals, paused-agent proposals and advise-only proposals are blocked.

Amount arguments use the tenant's currency in major units and at most two
decimal places; conversion to integer minor units uses `Decimal`. Explicit
foreign currencies are rejected. Credit amount and term digits must be stated
in the original request, so missing terms or amounts cannot be invented by the
model. Numeric-phrase grounding supports digits, comma separators, decimals,
`k`, `thousand` and `lakh`; unsupported word-number phrasing may need
clarification. Dates must be valid ISO dates in the planning horizon. An
explicit optional currency must match the tenant; there is no exchange-rate
calculation. What-if and live proposal calls cannot be mixed in one selection.

| Boundary | Limit |
|---|---:|
| User message | 2,000 characters |
| Model selections | 2 per rescue; 1 for ordinary requests |
| Calls in one selection | 4 |
| Calls in the whole model answer | 8 |
| Model output / final answer | 16 KiB each |
| One displayed tool result | 32 KiB; larger results become a hash and narrow-request message |
| Names in one list | 20; each name at most 160 characters |
| Generation | 400 tokens for planning, 600 for extraction |
| MLX queue / generation | 45 seconds each |
| Local-compatible HTTP request | 45 seconds including response-body reads; 256 KiB |
| Turn checks | 120 seconds before further selections or tools |

MLX streams generation and checks the deadline between tokens. Native model
loading, a single native compute operation and an individual deterministic
planner call cannot be forcibly preempted by these Python checks. A strict
wall-clock isolation boundary would require a supervised subprocess; that is
not claimed here. The planner's finite search limits still apply. Injected
generators are test callbacks, checked after return, not untrusted executables.

JSON must be one complete bounded object; prose fragments, duplicate keys,
nonfinite constants, extra plan fields and unknown tool/argument schemas fail
closed. Output budgets do not truncate or invent monetary values. Every
proposal still requires the existing authenticated human approval workflow,
PIN and any dual approval. Mandates, counterparty consent, idempotency, stale
state checks, kill switch and circuit breaker retain authority.

The optional local-compatible backend retains literal loopback-only HTTP,
explicit installed model IDs, no credentials/query strings, no redirects and
an unbenchmarked label. The released MLX adapter is identified by both file
hashes; a custom adapter is not labelled as the released v2 adapter. A matching
adapter hash identifies the artifact, not the accuracy of this new runtime.

## Evidence actually recorded

`evidence/upgrade-v1/model/injected_guard_report.json` records the independently
labelled containment suite and an observable rescue example using injected
JSON selections. It contains no real model inference. The tests cover a
result-aware rescue; no-gap and infeasible states; whole-plan validation;
ambiguous and hallucinated names; units, currencies and dates; missing credit
amount/terms; viewer/advise permissions; hypothetical isolation; constraint
preservation; malformed JSON; output/call limits; timeout containment; and
deterministic fallback labels. Finite passing tests are not proof of security.

`evidence/upgrade-v1/model/real_model_smoke.json` records macOS 26.6.2, arm64,
Python 3.14.7 and 10 logical CPUs. This machine has no `mlx`, `mlx-lm`,
`huggingface-hub`, released adapter or cached base model. The real smoke wrote
`device_verification_outstanding`, attempted zero real requests and exited 2.
No weights were downloaded and no model output, success or latency was
fabricated. Source hashes and dependency versions identify each recorded run.
The historical released v2 synthetic scores do not measure this runtime or a
different local model.

## Reproduce

From the project root, standard library only:

```bash
python3 scripts/smoke_reasoning.py --injected
python3 scripts/smoke_reasoning.py
python3 -m unittest discover -s tests -p 'test_reasoning_guards.py' -v
python3 -m unittest discover -s tests -p 'test_local_model.py' -v
python3 -m unittest discover -s tests -p 'test_tidelm_runtime.py' -v
```

The real smoke exits 2 when a model is unavailable, 1 when real requests fail
or mismatch, and 0 only when the authored smoke requests succeed. It sets
Hugging Face offline flags, so an absent base cache is never downloaded.
`--out` selects a separate evidence file when preserving a historical run.

On an Apple Silicon machine where the team chooses to provision the optional
model, follow `docs/SETUP_WINDOWS_MAC.md`: install `mlx-lm`, obtain the
checksum-verified released adapter with `python3 scripts/get_tidelm.py`, and
cache the exact base `mlx-community/Qwen3-4B-Instruct-2507-4bit` before running
the offline smoke. These provisioning steps use the network and were not run
for this upgrade. Record the actual model/adapter hashes, package versions,
all raw answers, mismatches and latency; do not silently substitute a base or
adapter. The smoke report records the installed adapter file hashes.

For an already-installed Windows/macOS compatible model, use its actual model
ID in the shell environment and preserve a separate report:

```bash
TIDEWAY_LOCAL_MODEL_URL=http://127.0.0.1:11434/v1 \
TIDEWAY_LOCAL_TEXT_MODEL=YOUR_INSTALLED_LOCAL_MODEL_ID \
python3 scripts/smoke_reasoning.py --out evidence/upgrade-v1/model/local-device-smoke.json
```

PowerShell can set the same variables using `$env:TIDEWAY_LOCAL_MODEL_URL` and
`$env:TIDEWAY_LOCAL_TEXT_MODEL` before the Python command. The script reads the
explicit shell environment; it does not rely on a private `.env` file. That
local model is unbenchmarked and does not inherit the TideLM release scores.
No Windows device or live compatible-model quality result is claimed.
