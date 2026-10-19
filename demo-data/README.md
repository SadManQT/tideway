# Viewing-only survey demo data

This folder contains a **fictional, deterministic viewing dataset**: 20
synthetic SME-finance viewers and 20 synthetic security-demo viewers. The rows
include varied task times, assistance, model availability, SUS answers,
security reactions and short humanized observations so the demo is not a wall
of identical perfect answers.

> **Not evidence.** These are generated personas, not people. They are not
> usability research, external security review, penetration testing, market
> research or model validation. Do not report the counts as observed results,
> do not submit them as participant evidence, and do not copy them into
> `evidence/private/`.

The project calls its user-study topic **SME Finance Copilot**. The request
used “SEM”, so this dataset interprets that wording as **SME**. Semantic
screening is a separate technical evaluation in the repository.

## What is here

| File | Purpose |
|---|---|
| `synthetic-surveys.json` | Complete structured dataset, including all 20 rows in each cohort and per-task/per-case behavior notes. |
| `sme-survey.csv` | One wide, spreadsheet-friendly row for each of the 20 SME viewers. |
| `security-survey.csv` | One wide, spreadsheet-friendly row for each of the 20 security viewers. |
| `summary.json` | Aggregate counts for the viewer; it repeats the synthetic-only disclaimer. |
| `index.html` | Local browser viewer with SME/Security tabs and participant detail cards. |

All IDs are fictional labels (`SME-01`…`SME-20` and `SEC-P01`…`SEC-P20`), not
names or a key to real people. The canonical user-study status remains
`pending_no_consented_participants` with zero real participants.

## Regenerate exactly

The generator uses only the Python standard library and has no random seed or
clock-dependent fields, so rerunning it produces the same files:

```bash
python3 scripts/generate_demo_surveys.py
```

It validates that there are exactly 20 rows per cohort, complete ten-item SUS
responses for the SME cohort, valid optional-model combinations, and all five
security cases for every security viewer.

## Watch the data

From the repository root, serve this folder locally:

```bash
python3 -m http.server 8788 --directory demo-data
```

Then open <http://127.0.0.1:8788/> and use the cohort tabs. The page is a
static viewer; it does not call a model, a cloud service, a bank or any remote
endpoint.

## Relationship to the real study kit

The real protocol and privacy boundary are documented in
[`docs/USER_STUDY_KIT.md`](../docs/USER_STUDY_KIT.md). Its fixed anonymous CSV
helper intentionally does not generate participants or free-text observations.
This folder is deliberately separate so the demo can look populated without
changing the honest readiness result in `evidence/readiness-v3/`.
