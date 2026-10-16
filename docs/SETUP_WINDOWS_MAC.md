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
python -m pip install mlx-lm
python scripts/get_tidelm.py
python run.py
```

MLX loads the base model on first use, which needs network and disk space.
Wait for warm-up before demonstrating it. The app's status card identifies an
unavailable model, and the deterministic assistant remains usable. The v2
metrics apply only to the released adapter and its synthetic evaluation.

For optional photos:

```
python -m pip install mlx-vlm Pillow
python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Qwen2.5-VL-3B-Instruct-4bit')"
python scripts/smoke_models.py
```

Check `THIRD_PARTY_NOTICES` before using the vision model. The smoke script
writes a new report and preserves the historical pre-fix observation. Inspect
actual draft dates and bill classification before claiming a successful repair.

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
device performance must be measured with the actual installed model.

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

Use `python` instead of `python3` where appropriate. The smoke command records actual model availability; it does not download weights or substitute another model. Current Mac arm64 checks used Python 3.14.7. The repository pins Python 3.11.11; this upgrade did not run Docker or another OS/device.

Optional photo/PDF visual QA can use an isolated environment (`python3 -m venv tmp/upgrade-venv`) and `requirements-evaluation.txt`. These dependencies are not needed for runtime. Tests on the base interpreter skip the four optional Pillow image tests; use an environment with Pillow to exercise them. Never infer post-change real model success from injected-output tests or optional-package installation.
