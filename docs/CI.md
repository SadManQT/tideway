# Continuous integration

The tracked workflow is [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). It runs on pushes, pull requests and manual dispatch. Adding it locally does not run GitHub-hosted CI; the first remote result exists only after the team publishes the workflow and GitHub executes it. No publish, deployment or submission step is included.

## Coverage

| Job | Checks |
|---|---|
| Standard library matrix | Python 3.11 and 3.14 on Ubuntu 24.04, Windows 2022 and macOS 14; compile, complete unit suite, 30-case task/security scorecard |
| Optional photo lane | Pinned Pillow dependency; image validation tests must import Pillow successfully |
| Browser and package lane | Workflow lint, Node 22 JavaScript syntax, headless Chrome desktop/mobile workflows, injected local-backend integration, linked payment delay, source package build and fresh extraction verification |

The core matrix uses `python -S`, which disables site packages. Photo tests may be skipped in that matrix; the separate Pillow lane exercises them. OS-specific symlink tests may be skipped when the runner cannot create symlinks. Counts and skip reasons are preserved in each job's uploaded test report rather than hardcoded into the workflow.

`PYTHONUTF8=0` deliberately keeps Windows locale file I/O active, and the Windows job asserts CP1252 coverage. This catches a recurrence of the multilingual JSON fixture decoding failure. `PYTHONIOENCODING=utf-8` makes console logs readable without changing the default file encoding.

The browser job finds the hosted image's installed Google Chrome and passes its absolute path through `CHROME`; the automation does not depend on an npm browser downloader. Node 22 supplies the built-in WebSocket used by the existing DevTools driver. Both browser runs use disposable synthetic databases. The local-backend run uses fixed test outputs and is **integration evidence, not real-model quality evidence**.

The package step requires passing tests and a browser report matching the current source digest. Extraction verification checks the path allowlist, exact manifest membership, byte counts, SHA-256 hashes, tests without Git/site packages, public guide routes and unauthenticated API refusal. CI publishes verification logs and manifests as temporary artifacts; it does not publish a submission ZIP or claim administrative readiness.

## Reproduce the checks locally

Run from the repository root using Python 3.11 or later:

```text
python -S -m compileall -q run.py tideway scripts tests
python -S scripts/verify_submission.py
python -S -m tideway.selftest
node scripts/check_javascript.mjs
node scripts/capture_screens.mjs --test-local-backend --out tmp/ci-local-backend
node scripts/capture_screens.mjs --test-payment-delay
python -S scripts/build_submission_package.py
python -S scripts/verify_package.py
```

The syntax runner discovers all `.js` and `.mjs` files below `web/` and `scripts/`, so extracting a new UI module does not require editing a fixed list in CI. Node 22 or later and Chrome/Edge are needed only for JavaScript/browser checks. Set `CHROME` or pass `--chrome` if the browser is outside the script's known locations. In a dedicated optional test environment, install `Pillow==12.3.0` and run `python -m unittest discover -s tests -p test_vision.py -v` without `-S`.

The workflow syntax can be checked with `go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.12`. The workflow and documentation are static files; the application's runtime remains standard library only.

## Maintenance and limits

Actions are pinned to full commit hashes, checkout credentials are not persisted and workflow token permissions are restricted to `contents: read`. The version comments identify the corresponding action major. Update the hashes deliberately after checking the official upstream action, then lint and review the workflow. Pillow is pinned separately from the core dependency-free runtime.

The matrix samples the minimum supported Python and a current Python release; it does not establish compatibility with every interpreter or machine. It does not download model weights, test MLX hardware inference, make cloud-model calls, connect to banks or use repository secrets. Hosted-runner availability, external action/dependency downloads and GitHub Actions settings are outside a local validation run. Passing CI is regression evidence for these checks, not a guarantee of no remaining errors or proof of security.

The workflow is based on the [official GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax), official [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python), [setup-node](https://github.com/actions/setup-node) and [upload-artifact](https://github.com/actions/upload-artifact) actions, and the [Ubuntu 24.04 hosted-image inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md). Action hashes and the installed-browser approach were checked against upstream on 2026-10-16.

## One frozen-source release

`python3 scripts/prepare_release.py` runs the local release sequence with cloud
credentials disabled, fresh synthetic databases and exact source hashes.
`--checks-only` omits browsers, PDFs and ZIP creation. `--reuse-pdfs` retains
previously reviewed PDFs. LF checks report offending paths without rewriting
them. Editing code during verification invalidates the run. Historical Windows
CRLF reports are preserved under `evidence/history/readiness-v2-windows/`; the
latest ZIP must match the current tests and browser stamp byte for byte. This
local command does not execute the GitHub-hosted OS matrix.
