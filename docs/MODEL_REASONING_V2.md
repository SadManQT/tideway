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
transcript. Result-aware tool selection has authored smoke evidence with a Windows compatible model. Post-change performance with the released MLX TideLM adapter remains unverified; those are different model identities.

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

## Optional structured plans

`TIDEWAY_LOCAL_STRUCTURED_PLANS=1` opts a compatible local text server into JSON Schema-constrained planning. The default is off. `tideway/plan_schema.py` describes the public tool union, argument types and limits; customer fields/maps can be closed to the scoped ledger's exact names. Optional nulls are permitted only where the existing tool validator treats them as omitted. The request uses `response_format: json_schema`; a server that does not support it fails without a loose retry.

The schema improves output shape. It does not establish user intent, financial correctness or permission: whole-plan preflight, number grounding, contextual dates/names, role checks and the approval workflow still apply. The same rules reject unsafe output even if a server ignores the schema. MLX generation and extraction keep their existing paths; the option does not silently replace the MLX adapter or add tools.

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
Python 3.14.7 and 10 logical CPUs. That recorded machine had no `mlx`, `mlx-lm`,
`huggingface-hub`, released adapter or cached base model. The real smoke wrote
`device_verification_outstanding`, attempted zero real requests and exited 2.
No weights were downloaded and no model output, success or latency was
fabricated. Source hashes and dependency versions identify each recorded run.
The historical released v2 synthetic scores do not measure this runtime or a
different local model.

Real compatible-model runs were subsequently recorded on Windows 11 x64 / Python 3.13.7 using checksum-pinned GGUF models and llama.cpp. The final Qwen3 4B runs used the explicit structured-plan option. All requests use synthetic businesses. The following results measure expected tool coverage for authored requests, not independent model accuracy:

| Recorded configuration/run | Matched authored requests | Preserved evidence |
|---|---:|---|
| Qwen2.5 1.5B, initial configuration | 3/6 | [windows-local-initial.json](../evidence/readiness-v2/model/windows-local-initial.json) |
| Qwen2.5 1.5B, subsequent prompt/harness | 2/6 | [windows-compact-round2.json](../evidence/readiness-v2/model/windows-compact-round2.json) |
| Qwen2.5 1.5B, structured output | 4/6 | [windows-compact-structured.json](../evidence/readiness-v2/model/windows-compact-structured.json) |
| Qwen3 4B, initial structured run | 5/6 | [qwen3-smoke.json](../evidence/readiness-v2/model/qwen3-smoke.json) |
| Qwen3 4B, final six-request smoke | 6/6 | [qwen3-final-smoke.json](../evidence/readiness-v2/model/qwen3-final-smoke.json) |
| Qwen3 4B, final expanded fixture | 12/12 | [qwen3-final-expanded.json](../evidence/readiness-v2/model/qwen3-final-expanded.json) |

An earlier expanded 12/12 run is also retained as `qwen3-expanded-smoke.json`; rerunning the same fixture does not create new independent cases. The final six requests completed seven generations; the expanded twelve completed fourteen because rescue requests can use a second selection. Both final reports recorded zero financial executions and zero issued mandates. Raw selections, deterministic tool results, mismatches, generation timing and source hashes are retained. The initial compact report predates the identity-reporting correction: its `requested_identity` incorrectly names TideLM; its `model_status` identifies the actual Qwen2.5 compatible model. It is retained as historical evidence, not an MLX adapter result.

Prompts/schema evolved after observing these cases, and the expanded authored set overlaps their intents. Neither set is a sealed benchmark or establishes generalisation, calibration, robust multilingual accuracy or full-model safety. The smaller profile's failures remain material. Native macOS helper execution, post-change MLX TideLM inference and post-fix TideVision inference remain outstanding. Historical MLX scores cannot be transferred to either GGUF profile.

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
The earlier Windows browser follow-up used a fixed-output local server for integration only. The subsequent real Windows smoke in the table is separate evidence; the UI test double does not supply its model-quality claim.

For the pinned profiles, provision explicitly using `scripts/local_demo_model.py --download`, then `--serve` in another terminal. `compact` remains the default; `--profile qwen3-4b` selects the measured larger model. `--cache-dir` can choose another drive, and must match between download and serve. Defaults use ignored `models/local-demo/`; weights/native runtimes are not bundled. The helper supports Windows x64 and macOS arm64/x64 but its native Mac path was not run here. Safe Mac TAR extraction needs Python 3.11.11+. See [SETUP_WINDOWS_MAC.md](SETUP_WINDOWS_MAC.md) for full commands, aliases and runtime requirements.

After starting the Qwen3 helper on port 8791, reproduce without overwriting the saved reports. Windows PowerShell:

```powershell
$env:TIDEWAY_LOCAL_MODEL_URL = 'http://127.0.0.1:8791/v1'
$env:TIDEWAY_LOCAL_TEXT_MODEL = 'Qwen3-4B-Instruct-2507-Q4_K_M'
$env:TIDEWAY_LOCAL_STRUCTURED_PLANS = '1'
python scripts/smoke_reasoning.py --out tmp/local-device-smoke.json
python scripts/smoke_reasoning.py --cases tests/fixtures/model_reasoning_smoke_v3.json --out tmp/local-device-expanded.json
```

On Mac, export the same three variables and use `python3` for both commands. This is a reproduction procedure, not a claim that Mac inference was executed. The harness records successful generations separately from deterministic responses and identifies the configured compatible model rather than the MLX adapter.
