# Run Tideway on Windows and macOS

## Core app on either machine

Use Python 3.11 or newer. The core app needs no pip installation and no API key.

Windows PowerShell:

```
python scripts/check_setup.py
python run.py
```

macOS Terminal:

```
python3 scripts/check_setup.py
python3 run.py
```

Open `http://127.0.0.1:8787`. Each machine keeps its own local database. Use
`--db data/fresh-demo.sqlite3 --port 8788` for a separate clean demo. Copy the
source ZIP between machines; do not copy real data, secrets or a running SQLite
database. The deterministic assistant and TidePay work on both platforms.

## Apple Silicon: evaluated TideLM v2 adapter

Use a dedicated environment and download the adapter once:

```
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install mlx-lm
python3 scripts/get_tidelm.py
python3 run.py
```

MLX loads the base model on first use, which needs network and disk space.
Wait for warm-up before demonstrating it. The app's status card identifies an
unavailable model, and the deterministic assistant remains usable. The v2
metrics apply only to the released adapter and its synthetic evaluation.

For optional photos:

```
python3 -m pip install mlx-vlm Pillow
python3 -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-VL-3B-Instruct-4bit')"
python3 scripts/smoke_models.py
```

Check `THIRD_PARTY_NOTICES` before using the vision model. The smoke script
writes a new report and preserves the historical pre-fix observation. Inspect
actual draft dates and bill classification before claiming a successful repair.

Post-change native MLX text and vision inference remain outstanding. The Windows compatible-model smoke below does not verify either Apple Silicon path.

## Optional checksum-pinned demo helper

`scripts/local_demo_model.py` provisions a compatible GGUF text model and a pinned llama.cpp runtime. It supports Windows x64 and macOS arm64/x64; native macOS arm64 provisioning and Qwen3 inference were measured in the sealed v3 challenge. Native MLX/TideLM and receipt inference remain separate. Use Python **3.11.11 or newer** for hardened TAR extraction on Mac. This optional requirement does not change the core app's Python 3.11+ support.

| Profile | Exact model alias | Model download |
|---|---|---:|
| `compact` (default) | `Qwen2.5-1.5B-Instruct-Q4_K_M` | 1,117,320,736 bytes |
| `qwen3-4b` | `Qwen3-4B-Instruct-2507-Q4_K_M` | 2,497,281,120 bytes |

The helper pins model revisions, sizes and SHA-256 hashes and verifies the native runtime archive. Before serving, it extracts a fresh private runtime so stale cached executables or DLLs cannot be selected. The server binds to `127.0.0.1`; Ctrl+C stops it. Weights and native runtimes are excluded from the source package. Neither profile is the released MLX TideLM adapter.

Default downloads use ignored `models/local-demo/`. `--cache-dir` explicitly chooses another directory/drive; use the same path and profile for download and serve. The download guard requires the artifact's size plus 512 MiB free headroom; allow additional space for the extracted runtime and sufficient inference memory. Downloads require network; subsequent verification and cached inference do not.

Windows PowerShell, terminal A (the drive/path is an example):

```powershell
python scripts/local_demo_model.py --download --profile qwen3-4b --cache-dir E:/Tideway-model-cache
python scripts/local_demo_model.py --serve --profile qwen3-4b --cache-dir E:/Tideway-model-cache --port 8791
```

Windows PowerShell, terminal B:

```powershell
$env:TIDEWAY_LOCAL_MODEL_URL = 'http://127.0.0.1:8791/v1'
$env:TIDEWAY_LOCAL_TEXT_MODEL = 'Qwen3-4B-Instruct-2507-Q4_K_M'
$env:TIDEWAY_LOCAL_STRUCTURED_PLANS = '1'
python run.py
```

macOS Terminal A (macOS arm64 helper and Qwen3 path verified; other hardware remains unverified):

```bash
python3 scripts/local_demo_model.py --download --profile qwen3-4b --cache-dir ~/Tideway-model-cache
python3 scripts/local_demo_model.py --serve --profile qwen3-4b --cache-dir ~/Tideway-model-cache --port 8791
```

macOS Terminal B:

```bash
export TIDEWAY_LOCAL_MODEL_URL=http://127.0.0.1:8791/v1
export TIDEWAY_LOCAL_TEXT_MODEL=Qwen3-4B-Instruct-2507-Q4_K_M
export TIDEWAY_LOCAL_STRUCTURED_PLANS=1
python3 run.py
```

For the smaller default profile, use `--profile compact` and its exact alias from the table. The compact model retained mismatches (3/6, 2/6 and 4/6 authored requests across successive configurations); it is not a verified substitute for the final 4B demo configuration. On Windows, `--cpu` selects a separate pinned CPU runtime; provide it on both download and serve when using that fallback.

Structured plans are **off by default**. Setting `TIDEWAY_LOCAL_STRUCTURED_PLANS=1` sends a scoped JSON Schema for text planning to a server that supports it. Unsupported servers fail without an unconstrained retry. This helps generation shape; the financial validators and human approval boundary remain authoritative.

The final Windows Qwen3 4B configuration matched [6/6 authored requests](../evidence/readiness-v2/model/qwen3-final-smoke.json) and [12/12 expanded requests](../evidence/readiness-v2/model/qwen3-final-expanded.json), after an initial 5/6 result. These overlapping synthetic smoke sets are not a model accuracy benchmark, device-performance guarantee or MLX adapter evaluation. All earlier failures remain linked in [MODEL_REASONING_V2.md](MODEL_REASONING_V2.md).

## Optional local model server on Windows or macOS

Tideway also supports a separately installed, trusted, OpenAI-compatible local
server such as Ollama or llama.cpp. Configure a model that the server actually
lists at `/v1/models`. Do not select a cloud model or a server that forwards
input elsewhere. Tideway connects only to a literal loopback HTTP address and
does not follow redirects. This boundary does not audit the local server itself.

Copy `.env.example` to `.env`, keep the cloud API key blank, and set:

```
TIDEWAY_LOCAL_MODEL_URL=http://127.0.0.1:11434/v1
TIDEWAY_LOCAL_TEXT_MODEL=YOUR_INSTALLED_LOCAL_MODEL_ID
TIDEWAY_LOCAL_VISION_MODEL=
```

Replace the example model ID with an actual installed model. To enable photos,
set `TIDEWAY_LOCAL_VISION_MODEL` to a vision-capable installed model and install
Pillow in Tideway's environment. Leave both model IDs blank to use the default
MLX/deterministic path. Restart Tideway after changing configuration.

This backend is labelled **Local model (unbenchmarked)**. It is not the
released MLX TideLM adapter, and it does not inherit its benchmark scores.
The same typed tool validator, role checks, draft confirmation and approval
rules apply. Transport/boundary tests use a local test server; model quality and
device performance must be measured with the actual installed model. The narrowly recorded Windows 4B smoke above does not establish compatibility or quality for other models/servers.

Server reference: https://docs.ollama.com/api/openai-compatibility

## Verify a machine

```
python scripts/check_setup.py
python scripts/verify_submission.py
python scripts/evaluate.py
python scripts/evaluate_scenarios.py
node scripts/capture_screens.mjs
python scripts/build_submission_pdfs.py
```

Use `python3` where that is the interpreter command. Browser/PDF tooling needs
Node 22+ and installed Chrome/Edge. Set `CHROME` for another Chromium executable.
`make` is optional. Runtime setup requires neither Node nor a browser driver.

## Contest upgrade verification

The new evaluation and linked demo commands use only the Python standard library:

```
python3 scripts/evaluate_tidepay_v2.py
python3 scripts/evaluate_upgrade_scenarios.py
python3 scripts/smoke_reasoning.py
python3 scripts/demo_payment_delay.py
node scripts/capture_screens.mjs --test-payment-delay --out tmp/delay-browser
python3 scripts/verify_package.py
```

Use `python` on Windows and `python3` on Mac. The smoke command records actual model availability; it does not download weights or substitute another model. Mac arm64 historical checks used Python 3.14.7; the Windows checks and real compatible-model smoke used Python 3.13.7. See `evidence/test-summary.json` and [READINESS_CURRENT.md](READINESS_CURRENT.md) for current scope and local interpreter checks. The repository pins Python 3.11.11; Docker was not tested because its daemon was unavailable. The [CI workflow](CI.md) is tracked and locally validated; no hosted CI execution is claimed.

Optional photo/PDF visual QA can use an isolated environment (`python3 -m venv tmp/upgrade-venv`) and `requirements-evaluation.txt`. These dependencies are not needed for runtime. A base interpreter without Pillow skips optional image tests; actual counts and reasons are recorded in each run. Never infer post-change real model success from injected-output tests or optional-package installation.

## Current release and evidence

Run `python3 scripts/prepare_release.py --checks-only` for offline checks, or
`python3 scripts/prepare_release.py` for browsers, five PDFs, ZIP and extraction.
Use `python` on Windows. This enforces LF source bytes and stops if files change
during verification. It never normalizes a hash to hide line-ending differences.
The [current readiness index](READINESS_CURRENT.md) links exact-artifact prediction
results and the first sealed actual Mac model run (28/32, four retained misses).
The optional compatible model remains distinct from historical MLX adapter scores.

Open `/guide.html` through the running app, for example
`http://127.0.0.1:8787/guide.html`; opening the file in Finder does not start Python.
