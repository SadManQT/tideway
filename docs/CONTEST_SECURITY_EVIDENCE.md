# Contest security evidence

Run the deterministic contest boundary checks and write the sanitized reviewer
artifact with:

```bash
python3 -m unittest tests/test_contest_security.py -v
python3 scripts/evaluate_contest_security.py
```

The evaluator writes `evidence/contest-security.json`. It runs SEC-01 through
SEC-05 against fresh in-memory fictional fixtures and records only boundary
statuses, counts, state-version checks and screening categories. The artifact
is **automated synthetic boundary evidence only**; it is not human, external,
penetration, real-model or production security validation.

## Supplied human security-task observations

The team additionally supplied 20 participant rows covering the same five
security scenarios and confirmed consent. It states these participants were not
involved in implementation. Ten overlap with the 20-person SME cohort, giving
30 unique people across the two reported cohorts. See the
[survey results](USER_STUDY_RESULTS.md) and
[security-task aggregate](../evidence/user-surveys/security-summary.json).

The CSV records scenario outcomes, assistance, timings and confidence responses.
It does not supply an external reviewer's qualifications, independent testing
scope or technical attack logs. These observations therefore do not replace an
independent penetration test or make the automated cases human security evidence.
