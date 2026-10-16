# Windows follow-up review - 16 October 2026

Environment: Windows 11, Python 3.13.7, Chrome 155.0.8059.82. This review uses
synthetic data and local disposable test databases.

## Fixes

- Explicit UTF-8 for sealed multilingual screening inputs and model smoke
  reports. The screening test previously raised `UnicodeDecodeError` under
  Windows' default CP1252 encoding.
- Explicit UTF-8 for package verification text inputs.
- The upgrade-summary generator now reports the measured environment without
  retaining a hard-coded claim that Windows was never tested.
- The existing local ZIP was an older 97-test version without the new upgrade
  scripts and contained a now-disallowed private-roster filename. The release
  was rebuilt with the current allowlist and public roster.

## Checks

- 159 tests: 158 passed, 1 skipped, 0 failures/errors. Windows symlink creation
  was unavailable; that skip is recorded in `evidence/test-run.log`.
- Desktop/mobile browser workflow passed without page errors, including linked
  payment delay, stale execution refusal, fresh approval, execution/read-back
  and public guide access. Current-source report:
  `evidence/screens/browser-verification.json`.
- A separate browser run passed using a fixed-output local-compatible server.
  That checks integration, not model accuracy or real model inference.
- The standalone linked payment-delay rehearsal passed.
- All 24 scenario outcomes and the screening confusion counts reproduced.
- TidePay's five model results reproduced on all 2,376 test invoices. The
  largest numeric difference from the saved Mac report was approximately
  1.8e-15. Federated MAE: 6.9568 days; heuristic MAE: 7.4107 days. These remain
  synthetic benchmark results; shipped model weights were not replaced.
- Python compilation and JavaScript syntax checks passed.
- Package byte integrity, isolated tests and fresh startup are checked with
  `python scripts/verify_package.py`. Consult `dist/extraction-verification.json`
  for the completed run and `dist/SHA256SUMS.txt` for the archive hash.

## Remaining limitations

- No post-change real TideLM/receipt-model inference has been demonstrated.
  The saved Mac smoke attempted zero real requests. Install/cache the exact
  models on the chosen device, then follow `docs/MODEL_REASONING_V2.md`.
- Injection screening misses 2/14 labelled attacks and flags 7/14 benign
  cases; payee screening misses 2/8 attacks and flags 3/8 benign cases.
  These are small synthetic sets. Approval and execution checks remain separate
  safeguards; screening is not complete fraud protection.
- Only 7/9 executed rescues meet the 10% simulated-risk target. Two remain at
  18.5% and 19%; correct handling does not mean every business is rescued.
- Leader, contribution roles, registration/eligibility, submission route and
  reviewer access still need team confirmation. Video recording remains
  deferred by the team. No push or submission was performed.
