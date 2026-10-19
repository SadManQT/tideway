# Team-reported current-UI usability retest

The team supplied two 20-row CSV files and subsequently confirmed that they describe real, completed sessions on 19 October 2026, moderated by Ramim. The English below incorporates that clarification and the later confirmation that the database was reset between participants. The calculated results remain unchanged. Collection and the tested build have not been independently verified. This retest is kept separate from the earlier team-reported study.

## Session and method

The following information is reported by the team. The machine-readable
[session metadata](../evidence/user-surveys/intake-20/session-metadata.json)
records its source, outstanding artifacts and scope.

| Field | Team-reported information |
|---|---|
| Study | Tideway current-UI usability retest |
| Session date | 19 October 2026 |
| Moderator | Ramim |
| Recruitment | Convenience sample of SME owners, bookkeepers and accountants; participants were not involved in implementing Tideway |
| Consent | Obtained before recording; covered anonymous task outcomes, timings, questionnaire responses and non-identifying observer notes |
| Database reset | The database was reset between participants, confirmed in the latest correction. Whether a separate database file was created for each person is unspecified; reset logs were not supplied |
| Task order | T1, T2, T3, T4, T5 |
| Timing | Stopwatch; active task time only |
| Assistance | One fixed hint after 60 seconds stuck |
| Failed and skipped tasks | Retained |
| Device | Windows laptop; Intel Core i5; 16 GB RAM |
| OS and browser | Windows 11; Microsoft Edge. Exact browser version was not supplied |
| Language and currency | Bangla or English, recorded per participant; BDT; selected-currency check included |
| AI model | Qwen3-4B-Instruct-2507, Q4_K_M |
| Runtime | llama.cpp b11678; local, inside Tideway through a loopback server |
| Fallback | Recorded separately and not counted as model success, according to the team; per-generation fallback records were not inspected |
| Tested commit / local changes | Not supplied; the current repository commit is not substituted for the session build |
| Collection | Outcomes and times were recorded during sessions. SUS was completed individually afterward, without coaching |
| Original records | The team states that observation sheets and unchanged exports were supplied. The two preserved CSV exports were inspected; separate observation sheets have not been identified in this intake |

The team states that model/runtime hashes were recorded in
`runtime-provenance.json`. A survey-linked copy has not been identified in this
intake. The existing v14 engineering runtime manifest belongs to a separate
model evaluation and is not treated as proof of the survey runtime. The exact
Edge version in the proposed `system-info.txt` also remains uninspected.

## SME records

All 20 consent cells in the archived SME snapshot say `YES`. Capitalization is normalized for analysis. The team additionally confirmed consent in its session statement; collection and consent were not independently observed.

| Task | Attempted | Without help | With help only | Failed | Median active seconds |
|---|---:|---:|---:|---:|---:|
| T1 - Payroll and reserve | 20 | 19 | 1 | 0 | 96.5 |
| T2 - Customer cash-risk evidence | 20 | 17 | 2 | 1 | 92 |
| T3 - Optional AI question | 17 | 16 | 1 | 0 | 107 |
| T4 - Rescue cost and remaining risk | 20 | 16 | 2 | 2 | 119 |
| T5 - Untrusted supplier message | 20 | 19 | 1 | 0 | 67.5 |

Across attempted tasks: **87/97 (89.69%) without assistance**, and **94/97 (96.91%) including assistance**.

Complete SUS questionnaires: 20; mean **75.75/100**. SUS is not a percentage of completed tasks.

T3: 2 unavailable-model and 1 unattempted records are excluded from its attempted denominator. The team reports local Qwen3-4B-Instruct-2507 inference inside Tideway. Survey-linked runtime hashes and per-generation fallback records have not been inspected; a questionnaire response alone does not verify a particular model invocation.

## Security assistance records

The source supplies assistance, times, confidence and narrative fields. It contains no structured technical outcomes. A record marked unassisted does not establish that a security control passed. Narratives remain private. The security CSV has no consent column; consent is attributed to the team's follow-up confirmation.

| Case | Records | Unassisted | Prompted once | Median seconds | Technical pass rate |
|---|---:|---:|---:|---:|---|
| SEC01 | 20 | 19 | 1 | 45 | Not measured |
| SEC02 | 20 | 18 | 2 | 62.5 | Not measured |
| SEC03 | 20 | 19 | 1 | 62 | Not measured |
| SEC04 | 20 | 19 | 1 | 53.5 | Not measured |
| SEC05 | 20 | 19 | 1 | 90.5 | Not measured |

Mean supplied confidence: **2.75 before**, **4 after**, on a 1-5 scale. Increased in 18 records; unchanged in 2; decreased in 0. This descriptive difference does not establish a causal effect.

## Source and interpretation

An earlier read in this intake showed SME consent=demo and security column example_behavior. The later supplied snapshots preserved here instead contain SME consent=YES and security column observed_behavior. The earlier bytes were not archived and their hashes are unknown. The team subsequently clarified that the data and session description refer to real, completed sessions, and asked that the English be corrected. This report preserves that attribution and the source history; collection has not been independently verified.

The team reports 20 SME participants and 20 security-task participants, with 10 overlapping and **30 unique people in this retest**, not 40. It supplied an anonymous correspondence for the overlapping records and states that no participants returned from the earlier study. These are team-reported counts. They are not merged with the earlier study to assert an independently verified cumulative sample.

These files followed illustrative data supplied in chat. The later explicit statement that the sessions were real is recorded as a team report. The earlier future-tense and demo/fictional wording has been corrected on that basis; the financial fixtures and actions remain fictional/sandboxed. No model output, technical pass rate, tested commit or unavailable artifact has been invented. Native MLX adapter/receipt verification and independent technical security review remain separate.

Original CSV bytes, the initial aggregate snapshot and reproduction helpers remain in the ignored private intake directory. The initial helper reproduces the pre-metadata analysis; the follow-up helper applies the attributed metadata. Existing earlier-study CSVs and aggregate counts are preserved. The public [analysis and source hashes](../evidence/user-surveys/intake-20/analysis.json) retain the same task/SUS/security calculations and link the metadata by its exact hash.

| Source | Records | SHA-256 |
|---|---:|---|
| sme-survey-20.csv | 20 | `c03c5de70709ada7bb8e9c268c31971f16d153b9b4975d78f3b9f4f8c95bedef` |
| security-survey-20.csv | 20 | `09d4ed2f042b5b61355cba077902d0bf296e07a55a3aa8de31ada9b4f2ff8f02` |
