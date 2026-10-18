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
