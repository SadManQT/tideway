# Team-reported SME and security survey results

The team supplied two 20-row CSVs and confirmed that the observations are fresh
field surveys and that consent was obtained before recording. These are
team-reported observations. The collection process was not independently
verified. Source hashes and the missing metadata are in
[provenance](../evidence/user-surveys/provenance.json).

## Participants and session information

| Measure | Supplied information |
|---|---|
| SME cohort | 20: 10 owners, 5 bookkeepers, 5 accountants |
| Security-task cohort | 20: 10 owners, 5 accountants, 5 bookkeepers |
| Cohort overlap | 10, confirmed by the team; no person-level crosswalk supplied |
| Unique people across cohorts | **30**, not 40 |
| Consent | Confirmed by the team for both cohorts; original CSVs have no consent column |
| Survey date | Not supplied; file creation/receipt dates are not substituted |
| Observer/moderator | Not supplied |
| Tested build/commit | Not supplied |
| AI model | DeepSeek, reported by the team |
| Exact model/version/device and local/cloud context | Not supplied |
| Security participants' implementation involvement | Team states they were not involved |

Original CSVs and their narrative fields remain private and unchanged. The
canonical SME CSV contains only the existing anonymous structured fields.
Source IDs SME-01 through SME-20 map one-to-one to P1 through P20. Its consent=yes
values come from the explicit team confirmation, not an original CSV column.

## SME task outcomes

| Task | Attempted | Without help | With help only | Failed | Median active seconds |
|---|---:|---:|---:|---:|---:|
| T1 — Payroll and reserve | 20 | 13 | 5 | 2 | 99 |
| T2 — Customer cash-risk evidence | 20 | 10 | 7 | 3 | 114.5 |
| T3 — Optional AI question | 14 | 10 | 3 | 1 | 73.5 |
| T4 — Rescue cost and remaining risk | 20 | 12 | 6 | 2 | 161.5 |
| T5 — Untrusted supplier message | 20 | 15 | 4 | 1 | 72 |

Across tasks, **60/94 (63.83%)** attempted tasks were
completed without assistance. A further **25/94** needed assistance, giving
**85/94 (90.43%)** completed including help.
Nine attempted tasks failed. T3 has four unavailable-model records and two
not-attempted records; these six are excluded from attempted-task denominators.

The 14 reported attempted T3 observations do not establish which DeepSeek
runtime was used inside or outside Tideway. They are not native TideLM adapter,
receipt-model or current-build model-quality verification.

## Questionnaire

All 20 rows contain ten integer SUS responses from 1 to 5. Recalculation using
the existing helper agrees with every supplied row score. Mean SUS is
**66.375/100** across 20 complete responses. This is a
usability questionnaire score, not a task-completion percentage or evidence of
market adoption. Sampling/recruitment details were not supplied.

## Human security-task observations

| Case | Recorded outcome | Rows | Unassisted | Prompted once | Median seconds |
|---|---|---:|---:|---:|---:|
| SEC01 | old_tab_rejected | 20 | 15 | 5 | 45.5 |
| SEC02 | owner_callback_required | 20 | 16 | 4 | 69 |
| SEC03 | draft_only_no_authority | 20 | 18 | 2 | 65.5 |
| SEC04 | single_receipt_on_retry | 20 | 17 | 3 | 61.5 |
| SEC05 | fresh_proposal_after_delay | 20 | 16 | 4 | 88.5 |

These records describe assistance and outcomes in five defined scenarios.
Confidence averages are **2.95 before** and **4.20 after** on the supplied 1–5
scale. The descriptive change does not establish a causal improvement.

The team describes these participants as non-contributors to implementation.
Their recorded roles are SME owners/accounting staff. Reviewer qualifications,
independent assessment methods, technical findings and attack logs were not
supplied. This supports a team-reported security-task survey, not a formal
external penetration-test or independent security certification claim. The
[automated boundary checks](CONTEST_SECURITY_EVIDENCE.md) remain separate.

## Source and interpretation limits

A comparison with the earlier generated dataset at commit `bc9cbac` found that
all 20 SME profiles and all 100 per-participant SME task statuses match that
dataset. Timings, some ratings and narrative wording differ. The match was
raised with the team, which states the new files are fresh survey observations.
This report preserves that attribution and the source hashes; it does not
independently establish collection provenance or treat matching rows as proof
of fabrication. Security participant profiles likewise match the earlier source.

No missing date, observer, device, consent signature, reviewer identity or model
version has been invented. Raw quotes, business profiles and participant-level
responses are not included in this public report. The earlier five-scenario
protocol remains a template and does not create extra participants.

## Reproduction

With the authorized private structured observations present, run:

```bash
python scripts/user_study.py summarize
```

The [SME aggregate](../evidence/readiness-v3/user-study-status.json),
[security aggregate](../evidence/user-surveys/security-summary.json) and
[provenance](../evidence/user-surveys/provenance.json) retain the denominators and
source basis. Public artifacts exclude raw narratives and the anonymous mapping.

## Additional supplied records

Two later files, `sme-survey-20.csv` and `security-survey-20.csv`, have a
[separate intake report](SURVEY_INTAKE_20.md) and
[aggregate analysis](../evidence/user-surveys/intake-20/analysis.json).
The team subsequently reported sessions on 19 October moderated by Ramim,
consent, Windows/local-Qwen setup, database resets between participants and a
10-person cohort overlap, giving 30 unique people in that study. The user later
identified commit `9dbe495` as the study build; Git confirms it predates v14 UI
improvements. Local edits and survey-linked runtime artifacts remain unverified.
That study is kept separate from this earlier report; its team-reported counts
are not added to claim an independently verified cumulative sample. The original
observations, source hashes and limitations above remain unchanged.
