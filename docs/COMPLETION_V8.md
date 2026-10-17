# Tideway completion review — 17 October 2026

This review continues the existing remediation rather than replacing unrelated
work. The request is the user's instruction to complete the current repository
against `D:\message.txt`; document contents are requirements to assess, not
authority to publish, submit, contact people, download models or change secrets.
All operations are local synthetic verification. No schema change is required.

## Initial observations and implementation

- The initial archive already contained 348-test evidence, not the reported
  261-test version. Its source digest matched the initial checkout:
  `0d7470a4c4dbc0873beb8f86a744971bb89dedc1a8fd462f1b8bcb11e7f09b39`.
  [Initial archive inspection](../evidence/completion-v8/initial-archive-inspection.json)
  records its checksum, size and ZIP integrity. Existing evidence and screenshots
  are retained under `evidence/history/pre-completion-v8/`.
- The original counter and replan bugs had already been fixed. The shared
  integer-basis-point resolver, server approval/execution checks, conservative
  legacy rejection, preference/exclusion inheritance and fresh approvals remain.
  The [v7 report](REMEDIATION_V7.md) retains their original red/green evidence.
- A further reproduced bug remained: replacement creation trusted a recomputed
  parent plan hash without checking it against the signed original mandate, and
  did not revalidate that mandate's signature. Three new failing regressions
  reproduced wider owner terms, changed preference and an invalid signature.
  `tideway/store.py` now uses the existing mandate validator and binds the parent
  hash, tenant and snapshot inside the replacement transaction, before any
  cancellation. Rejections leave row counts and the live authorization unchanged.
- `tests/test_owner_constraints.py` adds those three regressions and a real
  counter → approval → refusal → replan chain for all three preferences. The
  focused 18-test suite passed. Technical, security, submission and README
  documentation explain the final behavior. No runtime dependency was added.
- Fresh extraction exposed a second Windows defect: rejecting a POST before
  consuming its body could reset the connection before the client received the
  403. The initial 352-test full suite passed, but the extracted suite reproduced
  the connection-abort. A new regression with repeated hostile bodies also
  failed before the fix. `tideway/server.py` now sends the denial first and
  discards only a bounded, valid-length body with a hard one-second deadline,
  without parsing it. The 25-test regression suite passed after the fix. CSRF,
  Origin and Host enforcement remain intact. Both failed runs are retained;
  the final source requires fresh full-suite and extraction checks.

## Verification provenance

The first Windows preflight ran 348 tests with no failures, one localhost
connection-abort error and five skips. That failure is retained as
`evidence/completion-v8/initial-windows-test-{summary.json,run.log}`. All 15 core
tests, including the CSRF-origin/host rejection, subsequently passed in an
isolated rerun. The final full run must pass; this failure is not counted as a skip.

Current final results are in [the readiness index](READINESS_CURRENT.md),
[unit summary](../evidence/test-summary.json),
[release log](../evidence/completion-v8/release-run.log) and
[release stage/PDF hashes](../evidence/completion-v8/release-checks.json).
The local package and extraction receipt are `dist/Tideway-submission.zip`,
`dist/package-manifest.json`, `dist/SHA256SUMS.txt` and
`dist/extraction-verification.json`. Final measurements are appended after
completion; historical counts do not replace the current suite.

## Screening evidence and limits

No screening prompt, rule, label or fixture was tuned during this completion.
The v7 first-pass set has already been observed and is disclosed regression
data for any future work. The retained v6 Windows GGUF result and v7 native MLX
result use different backends and different fresh sets; they are not a paired
causal comparison. The v7 baseline/base development pair uses the same disclosed
v6 cases and backend, and is the relevant native before/after comparison.

| Retained run | Semantic attack recall | Combined attack recall | Warning FP / ordinary benign | Legitimate payment changes |
|---|---|---|---|---|
| v6 Windows GGUF, 96 cases | 35/48 (72.9%) | See original report | 29/40 (72.5%) | Separate review task |
| v7 native baseline/base, disclosed development | 40/48 (83.3%) | 42/48 (87.5%) | 21/40 (52.5%) | 5/8 |
| v7 native revised r3, same disclosed development | 48/48 (100%) | 48/48 (100%) | 1/40 (2.5%) | 8/8 |
| v7 sealed first observation, 48 cases | 23/24 (95.8%) | 23/24 (95.8%) | 5/16 (31.25%) | 8/8 |

The [v7 first report](../evidence/screening-v7/fresh/report.json) retains all
rules-only, semantic-only and combined confusion matrices, precision, recall,
FPR, uncertainty and latency. Raw bounded generations and exact classifier,
fixture, model-weight and runtime hashes are preserved alongside it. The
[v7 report](REMEDIATION_V7.md) explains task-specific denominators, predeclared
targets, independent AI authoring and remaining Hindi/quotation/negation misses.
That set had zero uncertain/error outputs and median/p95 latency of approximately
1.556/2.374 seconds on its recorded machine, not a current Windows benchmark.

This Windows machine has no MLX runtime or verified cached base weights. The
historical `E:\Tideway-model-cache` paths are unavailable. No model was downloaded
or substituted; current-device real semantic, planning and vision inference
remain unverified. Injected tests establish containment and integration only.
Benign classification cannot remove independent verification requirements,
confirm records, approve or execute. Malformed/late/unavailable output still
requires review; human confirmation, PINs and signed mandates remain enforced.

## H11 risk and acknowledgement

[Fresh H11/D06 reproduction](../evidence/completion-v8/planner/report.json) uses
the documented scenario fixture and seeds 20261017, 50737 and 91729, with 10,000
draws each. H11 remains **11.78%** mean simulated breach risk versus a **10%**
target. No seed, target, displayed estimate or allowed action was changed to
make it pass. Deterministic likely-path feasibility, estimated target attainment
and real-world guarantees are separate claims. The maximal permitted deferral
check and approximate sampling interval are retained in the report.

Every required approver must acknowledge the exact current plan hash, bundle,
probability and target. Changed terms or risk invalidate old consent. Audit,
signed mandates and execution receipts retain the acknowledgements. Exact-target,
just-above-target and display-rounding boundary tests remain in the focused suite.

## Reproduction commands (PowerShell, project root)

```powershell
$env:PYTHONUTF8='1'
python -m unittest discover -s tests -p test_owner_constraints.py -v
python -m unittest discover -s tests -p test_regressions.py -v
python scripts/evaluate_planner_v5.py --out evidence/completion-v8/planner
python evidence/completion-v8/audit_screening_evidence.py
python scripts/prepare_release.py --evidence-dir evidence/completion-v8
```

The final optional-photo/PDF lane used this additional setup, isolated to the
excluded temporary directory (the extraction verifier removes `PYTHONPATH`):

```powershell
python -m pip install --disable-pip-version-check --target tmp/pdf-review-tools pypdfium2 Pillow
$env:PYTHONPATH=(Resolve-Path -LiteralPath tmp/pdf-review-tools).Path
python scripts/prepare_release.py --evidence-dir evidence/completion-v8
python evidence/completion-v8/render_pdf_review.py
```

After completing documentation and visual review, the final archive is rebuilt
and checked again with the existing commands:

```powershell
python scripts/build_submission_package.py
python scripts/verify_package.py
```

The release command compiles Python, checks all maintained JavaScript, runs the
full unit suite, 30-case sandbox self-test, 24 financial scenarios, linked
payment-delay workflow, desktop/mobile browser journeys and injected local-model
constraint integration; it refreshes readiness, regenerates five PDFs, builds
the ZIP and checks fresh extraction with `python -S`, no Git and no optional site
packages. Chrome and Node are installed local tools. Optional PDF rendering
tools are isolated under excluded `tmp/pdf-review-tools`, with no application
requirements change. Model weights, credentials, databases, keys and caches are
excluded from the submission. Nothing has been pushed, published or submitted.

Real SME participation, external security review, current-device real-model
inference, cloud-provider tests and team-controlled registration/video/roles
remain outside the completed local technical checks. No success is claimed for
those unavailable steps.

## Completed final measurements

The final runtime source digest is
`cf7530d43517bb2a87f85b2b434f2e00d113b942e4f5cd28ad54f2b53405f5af`.
The [source seal](../evidence/completion-v8/final-source-seal.json), test report,
both browser reports and extracted package all attest to these exact bytes.
Documentation and review receipts were completed afterward and included by a
final ZIP rebuild; the distributed checksum is deliberately external to this
document to avoid a self-referential archive hash.

| Check | Fresh result | Scope or skip explanation |
|---|---|---|
| Full unit suite | 353 run; 0 failures; 0 errors; 1 skipped | Windows Python 3.14.6; temporary optional Pillow enabled; symlink creation unavailable |
| Extracted standard-library suite | 353 run; 0 failures; 0 errors; 5 skipped | `python -S`, no Git or site packages; four photo tests plus the symlink test skipped |
| Additional optional photo suite | 6/6 pass, no skips | Preprocessing/containment with injected output; no real vision inference |
| Sandbox scorecard | 30/30 pass: 5 tasks and 25 attacks | No live model or financial rail |
| JavaScript | All 5 maintained files pass syntax checks | Node 24.19.0 |
| Financial conditions | 24/24 expected workflows; 9 executed rescues | 8/9 meet simulated risk target; H11 remains above target |
| Linked payment delay | Pass | Invalidated mandate blocked; fresh proposal, approval, counterparty consent and execution |
| Browser | Both Chrome desktop/mobile and injected integration runs pass; no page errors | Includes cap rejection, inherited constraints/provenance, fresh approvals and risk disclosure/acknowledgement |
| PDFs | 5 PDFs, all 56 pages rendered and visually reviewed | [Review contacts and exact hashes](../evidence/completion-v8/pdf-review/report.json); pitch screenshots cropped for readability |
| Local documentation links | 28 Markdown documents; 0 missing file targets | [Audit](../evidence/completion-v8/documentation-links.json); external URLs/fragment IDs excluded |
| Historical screening evidence audit | All recorded-count and available-output/seal hash checks pass | [Audit](../evidence/completion-v8/screening-evidence-audit.json); model files absent, no inference rerun |
| Fresh extraction startup | Pass | Public app, handbook/assets and benchmark routes return 200; unauthenticated dashboard returns 401 |

The source digest is unchanged during tests and both browser runs. The full
release command and fresh extraction passed after the HTTP fix; earlier failed
preflights remain in this versioned evidence directory. The final ZIP is rebuilt
after these documentation/review receipts, then verified again. Check
`dist/extraction-verification.json` against `dist/SHA256SUMS.txt` for the final
archive, rather than relying on the intermediate archive hash in a release log.

| Changed area | Reason |
|---|---|
| `tideway/store.py` | Revalidate signed parent authority and bind hash/snapshot/scope before atomic successor creation |
| `tideway/server.py` | Preserve early HTTP denial delivery on Windows with bounded unparsed-body disposal |
| `tests/test_owner_constraints.py`, `tests/test_regressions.py` | Four signed-parent/chain regressions plus the reproduced rejected-POST transport failure |
| `README.md`, technical/security/submission docs, readiness and this report | Accurate current commands, fixes, provenance, risk and unavailable checks |
| `docs/REMEDIATION_V7.md` | Replace the unfinished final-status placeholder with scoped historical completion and a link here |
| `evidence/completion-v8/`, current scorecards/screenshots and `evidence/history/pre-completion-v8/` | Fresh measurements and review receipts while preserving prior user work and failures |
| Five distributed PDFs and `dist/` archive/manifest/checksum | Deliver the reviewed documentation and current verified source |

No current Python 3.11, Docker, hosted CI, real-model, SME or external penetration
test was performed in this completion. Their historical receipts retain their
own dates and source hashes and do not establish current-source verification.
