# Additional supplied survey records

Two additional 20-row CSV files were supplied for analysis. The tables below describe the supplied records. Session date, moderator, tested build, exact AI runtime and cross-cohort overlap were not supplied. This intake does not replace or add participants to the earlier team-reported study.

## SME records

All 20 consent cells in the archived SME snapshot say `YES`. Capitalization is normalized for analysis; this is a declaration in the source, not independent consent verification.

| Task | Attempted | Without help | With help only | Failed | Median active seconds |
|---|---:|---:|---:|---:|---:|
| T1 - Payroll and reserve | 20 | 19 | 1 | 0 | 96.5 |
| T2 - Customer cash-risk evidence | 20 | 17 | 2 | 1 | 92 |
| T3 - Optional AI question | 17 | 16 | 1 | 0 | 107 |
| T4 - Rescue cost and remaining risk | 20 | 16 | 2 | 2 | 119 |
| T5 - Untrusted supplier message | 20 | 19 | 1 | 0 | 67.5 |

Across attempted tasks: **87/97 (89.69%) without assistance**, and **94/97 (96.91%) including assistance**.

Complete SUS questionnaires: 20; mean **75.75/100**. SUS is not a percentage of completed tasks.

T3: 2 unavailable-model and 1 unattempted records are excluded from its attempted denominator. The model identity and local/cloud context are unknown.

## Security assistance records

The source supplies assistance, times, confidence and narrative fields. It contains no structured technical outcomes. A record marked unassisted does not establish that a security control passed. Narratives remain private. Consent for this separate intake is not documented in this file.

| Case | Records | Unassisted | Prompted once | Median seconds | Technical pass rate |
|---|---:|---:|---:|---:|---|
| SEC01 | 20 | 19 | 1 | 45 | Not measured |
| SEC02 | 20 | 18 | 2 | 62.5 | Not measured |
| SEC03 | 20 | 19 | 1 | 62 | Not measured |
| SEC04 | 20 | 19 | 1 | 53.5 | Not measured |
| SEC05 | 20 | 19 | 1 | 90.5 | Not measured |

Mean supplied confidence: **2.75 before**, **4 after**, on a 1-5 scale. Increased in 18 records; unchanged in 2; decreased in 0. This descriptive difference does not establish a causal effect.

## Source and interpretation

An earlier read in this intake showed SME consent=demo and security column example_behavior. The later supplied snapshots preserved here instead contain SME consent=YES and security column observed_behavior. The earlier bytes were not archived and their hashes are unknown. Changed labels alone do not establish collection provenance.

Overlap between these two cohorts and overlap with the earlier survey are unknown. Different anonymous IDs do not prove different people. The earlier reported overlap is not reused for this intake.

These files followed illustrative data supplied in chat. Their labels and rows are retained as supplied, without claiming they establish a fresh field survey. No metadata, model run, participant quotation or technical result has been invented.

Original CSV bytes and a reproduction helper remain in the ignored private intake directory. Existing survey CSVs, aggregate counts, reports and historical results are preserved. The public [analysis and source hashes](../evidence/user-surveys/intake-20/analysis.json) contain aggregates only.

| Source | Records | SHA-256 |
|---|---:|---|
| sme-survey-20.csv | 20 | `c03c5de70709ada7bb8e9c268c31971f16d153b9b4975d78f3b9f4f8c95bedef` |
| security-survey-20.csv | 20 | `09d4ed2f042b5b61355cba077902d0bf296e07a55a3aa8de31ada9b4f2ff8f02` |
