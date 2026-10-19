# Customer payment decisions and screening precision

The customer review now answers two questions together: when a receipt is
expected relative to payroll, and what the customer's observed payment history
actually shows. Rescue cards and the approval dialog show the same stored
economic cost, lowest likely cash, reserve floor and simulated remaining risk.

## Customer evidence and review

- Simple and detailed Cash weather views show exact late/settled counts using
  payments observed by the current simulation date. Future settlements do not
  enter the displayed history. Missing/thin history is explicit.
- Receipt dates and amounts come from production projection events, including
  promises, discounted early-payment agreements and after-horizon receipts.
  Proposed actions are not counted as collected cash. A same-day receipt warns
  that daily closing cash does not establish intraday payroll funding.
- Links open the exact invoice or that customer's invoice history. Opening a
  review does not save, approve, execute or change financial records.
- Rescue review explains economic cost versus exposure and shows the actual
  remaining probability, including above-target precision. An infeasible option
  remains unapprovable. Every required risk acknowledgement, PIN, second approval
  and counterparty agreement is unchanged.
- Selected display currency applies to the new monetary figures. Native signed
  terms and exact ledger values are unchanged. English/Bangla customer cards,
  mobile layout and the approval dialog are exercised in the browser checks.

These are engineering changes motivated by the supplied T2/T4 observations.
The existing SUS and human task-completion figures have not been remeasured.
A real participant retest is still required to measure usability improvement.

## Screening changes

Routine invoice approval, reconciliation, account managers/balances and bank
holidays are separated from changes to payment destination identifiers.
Non-payment noun masks apply only to payment-change heuristics; attack patterns
still examine the original clause. An active payment change elsewhere still
requires review, including proposed, conditional and future changes.

The semantic decision procedure tests attack categories before payment updates.
It distinguishes the special `review` payment-change label from the ordinary
human confirmation required for every draft. Typed schemas, one bounded local
generation, timeout/error review, retained outputs and the rule/model union
remain enforced. A benign judgement never removes rule flags or grants authority.

The old broad redirection rule incorrectly classified a legitimate callback-gated
account update as an attack. It now requires an explicit unsafe replacement or
verified-destination substitution; the legitimate change keeps its verification
flag. Existing substitution, bypass, quote-following and exfiltration regressions
are retained. Bangla personal-data export and Hindi fabricated authority receive
additional bounded rules and semantic examples.

## Actual inference and retained first observations

Cached Windows compatible `Qwen3-4B-Instruct-2507-Q4_K_M` was launched after
verification of pinned model/runtime SHA-256 values. No model download occurred.
[Runtime provenance](../evidence/upgrade-v14/runtime-provenance.json) identifies
the artifacts. This is not the native MLX classifier, TideLM adapter or receipt
model; the historical native 31.25% warning false-positive observation is retained.

| Observation | Attacks detected | Legitimate changes reviewed | Unnecessary warnings / ordinary benign |
|---|---:|---:|---:|
| Paired baseline, 48 development cases | 16/16 | 8/8 | 17/24 |
| Final implementation, same 48 cases | 16/16 | 8/8 | 0/24 |
| Initial 120 disclosed regressions, before final fixes | 50/52 | 20/20 | 0/48 |
| First new 48-case challenge, before final fixes | 15/16 | 8/8 | 0/24 |
| Final 168 now-disclosed regressions | 68/68 | 28/28 | 0/72 |

The first challenge was authored by the same implementation-aware maintainer,
with texts, labels, classifier hashes and targets sealed before inference.
It is a source-aware AI-authored synthetic challenge, not independent/blind or
population validation. Its predeclared targets were at least 90% combined attack
recall, at most 10% ordinary-benign warning false positives and full legitimate
payment-change review on this set. The first observation met those targets but
missed one Hindi forged-payment request.

Two earlier regression misses involved Bangla concealed contact-list export and
Hindi evidence removal/approval fabrication. All three were fixed and promoted
to regression coverage. Their original generations and scores remain intact.
The final 168 cases include the now-observed challenge, so their perfect recorded
result is a known-case regression result, not fresh accuracy.

Evidence: [reconciled summary](../evidence/upgrade-v14/screening-summary.json),
[baseline](../evidence/upgrade-v14/screening-baseline/report.json),
[initial revision](../evidence/upgrade-v14/screening-revised/report.json),
[initial known set](../evidence/upgrade-v14/screening-final-known/report.json),
[first challenge](../evidence/upgrade-v14/screening-challenge/report.json),
[post-fix known set](../evidence/upgrade-v14/screening-post-fix-known/report.json).
Each folder retains bounded raw generations, per-case results, fixture hashes,
runtime identity, timestamps and source-integrity flags. Paired comparisons
check identical case texts/labels and backend identity.
Raw observation JSONL files disable Git text normalization so the sealed byte
hashes also reproduce after a fresh checkout on another operating system.
The [byte-preservation check](../evidence/upgrade-v14/git-byte-preservation.json)
compares the original sealed hashes, working files and Git blobs.

## Verification and reproduction

```bash
node scripts/test_decision_review.mjs
python -m unittest discover -s tests -p test_decision_review.py
python -m unittest discover -s tests -p test_screening_precision_v14.py
python scripts/summarize_screening_precision.py
python scripts/prepare_release.py --reuse-pdfs
```

For actual inference, configure the pinned local server as documented in
[setup](SETUP_WINDOWS_MAC.md), then use `evaluate_screening_followup.py` with a
new output directory. Existing observations are never overwritten. Previously
observed challenge texts must be called disclosed regressions when rerun.

The [readiness index](READINESS_CURRENT.md),
[full unit receipt](../evidence/test-summary.json),
[browser receipt](../evidence/screens/browser-verification.json) and
[release stages](../evidence/upgrade-v14/release-checks.json) identify their tested
source. `dist/extraction-verification.json` records the rebuilt ZIP's hash,
extracted tests and fresh startup. Earlier visually reviewed PDFs are reused;
the new interface and measurements are described here. No fresh native Mac,
external penetration test or human usability result is implied.
