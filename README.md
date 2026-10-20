<div align="center">

<img src="docs/media/hero.svg" alt="Tideway: sees the cash gap coming, plans the rescue, lets people decide" width="100%">

<br>

![Python](https://img.shields.io/badge/python-3.11%2B-0b2a45?logo=python&logoColor=white)
![Runtime dependencies](https://img.shields.io/badge/runtime%20dependencies-none-1f8a96)
![Tests](https://img.shields.io/badge/tests-557%20passing-1f8a96)
![Self-test](https://img.shields.io/badge/attacks%20blocked-25%2F25-d4a72c)
![License](https://img.shields.io/badge/license-MIT-0b2a45)

**FinTechathon 2026 · International Track · Topic E: SME Finance Copilot**<br>
Built by **The Last BrainCell** · Bangladesh University of Engineering and Technology (BUET)

[Quick start](#quick-start) · [See it in action](#see-it-in-action) · [Features](#everything-tideway-does) · [Our AI](#tideways-own-ai) · [Security](#security-by-design) · [Docs](#documentation)

</div>

---

## Why Tideway

> A profitable small business can still miss payroll. Customers pay late, suppliers expect to be paid on time, and the gap lands on payroll day. Most owners only see it when it is already too late to act.

**Tideway is an AI financial participant with hard limits.** It forecasts the cash gap days ahead, predicts which customers will pay late, and plans the cheapest safe rescue. Then it stops. **People approve** with a PIN, large amounts need **two people**, and only a **signed, expiring mandate** can execute, once, with proof.

<img src="docs/media/flow.svg" alt="How Tideway works: see, predict and propose by AI; approve, execute and prove by people and signed mandates" width="100%">

## Who it helps

<img src="docs/media/audience.svg" alt="Who Tideway helps: SME owners, finance teams, banks and lenders, large buyers and auditors" width="100%">

| Who | Their problem | How Tideway helps |
|---|---|---|
| **SME owner** | Payroll surprises, no time for spreadsheets | A 14-day cash forecast with the odds of a shortfall, a ranked rescue plan and answers in their own language |
| **Finance team** | Manual data entry, duplicate or redirected payments | Zero-entry inbox, 13-week cash flow, payment-integrity scan and maker-checker approvals |
| **Bank or lender** | Late, unreliable signals of SME distress | A portfolio radar that ranks clients by breach risk, and credit passports verified offline with a public key |
| **Large buyer** | A small supplier's cash crunch breaks the supply chain | Early warning on suppliers heading for a gap, and two-business negotiation that protects both payrolls |
| **Auditor** | AI actions that cannot be traced | Every step signed, hash-chained with an independent witness and replayable; a one-click tamper drill |

## See it in action

<table>
<tr>
<td width="50%" valign="top"><b>Cash weather</b><br><img src="docs/media/cash-weather.gif" alt="Cash weather forecast" width="100%"><br><sub>Lowest-cash day, reserve gap and the odds of a shortfall across 1,000 simulated futures, 14 days ahead.</sub></td>
<td width="50%" valign="top"><b>Ask in your language</b><br><img src="docs/media/ask-tideway.gif" alt="Ask Tideway in Chinese" width="100%"><br><sub>Ask in English, 中文, Español, Français, Português, Bahasa, Hinglish or Banglish. Every number comes from Tideway's own tools.</sub></td>
</tr>
<tr>
<td valign="top"><b>Approve exactly this</b><br><img src="docs/media/approve.gif" alt="Approval with PIN" width="100%"><br><sub>Read the exact terms, type the exposure and step up with your PIN. Large plans need a second person.</sub></td>
<td valign="top"><b>Fraud and injection blocked</b><br><img src="docs/media/quarantine.gif" alt="Quarantined records" width="100%"><br><sub>A changed bank account, a look-alike payee and a poisoned bill are blocked; message text never gains authority.</sub></td>
</tr>
<tr>
<td valign="top"><b>Treasury hub</b><br><img src="docs/media/treasury.gif" alt="Treasury hub" width="100%"><br><sub>13-week cash flow, working-capital health score, payment-integrity scan and a public-key signed credit passport.</sub></td>
<td valign="top"><b>Portfolio radar for lenders</b><br><img src="docs/media/portfolio-radar.gif" alt="Portfolio radar" width="100%"><br><sub>Early warning across 60 businesses: tiers, drivers and an economic-shock stress test.</sub></td>
</tr>
<tr>
<td valign="top"><b>Every page explains itself</b><br><img src="docs/media/help-layer.gif" alt="Plain-language help and tour" width="100%"><br><sub>A "What is this page?" card, tap-to-explain finance terms and a one-minute tour, so anyone in the company can use it.</sub></td>
<td valign="top"><b>Proof, not promises</b><br><img src="docs/media/evidence.gif" alt="Tamper drill" width="100%"><br><sub>A hash-chained audit log with an independent witness; the tamper drill shows detection at the exact entry.</sub></td>
</tr>
</table>

## Everything Tideway does

**For the business**

- **Cash weather.** Exact daily cash projection in integer minor units; scheduled, likely and stress scenarios; 1,000 seeded simulations; a 14-day look-ahead so a deferral cannot hide a gap just past the target date.
- **TidePay predictions.** Every open invoice gets a probability for each lateness band, learned from payment histories.
- **Rescue plan.** An exact optimiser over supplier deferrals, early-payment discounts (priced as an annual rate) and zero-cash reminders. Simulated counterparties accept, counter-offer or refuse; a counter becomes a new proposal that needs fresh approval.
- **Ask Tideway.** Plain-language questions in eight languages, with the tool plan shown under every answer. Works with or without a language model installed.
- **Zero-entry inbox.** Paste bank, card and mobile-money alerts (bKash, M-Pesa, UPI, Alipay, WeChat Pay, PayNow, GCash, Pix, Wise, SEPA and more); get draft records. Nothing is saved until a person confirms.
- **What-if and Decision lab.** Find a plan's breaking point, stress accepted agreements, compare recovery options, replay a private capsule, inspect exactly what an optional cloud model would see, and negotiate terms that protect two businesses at once.
- **Treasury hub.** A 13-week cash flow that reconciles exactly with the daily projection; a 0-100 working-capital health score with every formula and weight shown; a payment-integrity scan for duplicates, split bills, outliers and changed payees; a credit passport with an Ed25519 public-key signature.

**For lenders and large buyers**

- **Portfolio radar.** Ranks every client by breach probability, days to the gap and main driver; red, amber and green tiers; a shock slider shows who moves into danger. It runs on its own portfolio and never reads tenant workspaces.
- **Verifiable credit passport.** A lender checks a passport offline with the issuer's public key, without contacting Tideway: `python scripts/verify_passport.py passport.json`.

**For everyone in the company**

- **Plain-language help** on every page, about 40 finance terms explained on tap, a guided tour and a larger-text mode.
- **Workspaces and roles.** Sign up a business in any of 29 currencies, invite your accountant by one-time code, and keep tenants fully isolated.
- **Exports.** Evidence JSON, records and receipts CSV (spreadsheet-formula-safe), a 13-week cash-flow CSV, a bank pack and a draft ISO 20022 `pain.001` payment file that is never sent.

## Tideway's own AI

Trained by the team, running on the device. The language model can only propose; validators, permissions and people decide.

| Model | What it does | Result on held-out synthetic tests |
|---|---|---|
| **TidePay** | Predicts how late each invoice will be paid (federated training across 40 simulated SMEs) | Mean error **8.56 days** vs 10.23 for a history heuristic, on 7,427 unseen invoices |
| **TideLM** (Qwen3-4B + LoRA, Apple Silicon) | Turns questions and pasted alerts into typed tool plans and draft records | Exact plans **26.7% → 96.7%**, extraction F1 **0.83 → 0.969** |
| **TideLM** (Qwen3-1.7B + LoRA, NVIDIA RTX 3060 Ti) | The same task, trained in **7.3 minutes** on a consumer GPU | Exact plans **21.3% → 92.7%**, extraction F1 **0.30 → 0.99**, injection flags **62% → 100%** |

Details: [model card](docs/MODEL_CARD.md) · [GPU training](docs/TIDELM_CUDA.md) · [TidePay evaluation](docs/DEPLOYED_MODEL_EVALUATION.md)

## Security by design

> **The golden rule:** no text, message or model output can approve or execute a payment. Moving money is never delegated to the AI.

| Control | What it does |
|---|---|
| **Permission tiers** | The agent can read and propose only. It has no approve, execute, SQL, shell or URL tool. |
| **Maker-checker + PIN step-up** | Large plans need two people, one of them the owner, plus a typed exposure amount. |
| **Signed, single-use mandates** | HMAC-signed, bound to the exact actions, snapshot and policy; they expire and execute once with read-back. |
| **Kill switch and circuit breaker** | The owner can pause the agent instantly; repeated security denials pause it automatically. |
| **Payee fraud blocks** | Changed bank details or look-alike names block the bill until verified by callback; separation of duties. |
| **Injection quarantine** | Suspicious text is kept as data in eight languages and never treated as an instruction. |
| **Tamper-evident audit** | Hash-chained log with an independently keyed witness; truncation and edits are detected. |
| **Tenant isolation** | Membership and role are checked on every request; loopback-only server, strict CSP, CSRF and rate limits. |

[Security report](docs/security-report-lean.pdf) · [Security self-assessment](docs/SECURITY_SELF_ASSESSMENT.md)

## Architecture

```mermaid
flowchart LR
    UI["Browser UI<br/>vanilla JS, no build step"] -->|"CSRF · CSP · roles · tenant checks"| S["server.py<br/>loopback only"]
    S --> AG["Rescue agent + planner<br/>read / propose only"]
    S --> LM["TideLM or built-in rules<br/>typed plans, draft records"]
    AG --> EN["Projection · Monte Carlo · TidePay"]
    S --> TH["Treasury hub · Portfolio radar"]
    AG -->|proposal| HU{"People approve<br/>PIN · two-person"}
    HU -->|"signed mandate"| EX["Sandbox execution<br/>once · read-back"]
    EX --> AU[("Hash-chained audit<br/>+ witness")]
```

Pure Python standard library at runtime: no packages, no API keys and no internet needed for the core app.

## Quick start

```bash
git clone https://github.com/SadManQT/tideway.git
cd tideway
python run.py
```

Open <http://127.0.0.1:8787> and click **Nadia (Owner)**. Demo PINs: Nadia `2468` (owner), Imran `1357` (accountant), Guest `0000` (viewer).

**A two-minute tour:** check **Cash weather** → ask **Ask Tideway** a question in another language → run the **Rescue plan** and approve with Nadia, then Imran → paste the injection sample into **Inbox** → run the **Security centre** self-test → open **Treasury** and **Portfolio radar** → run the **Evidence** tamper drill.

```bash
docker build -t tideway:local . && docker run --rm -p 127.0.0.1:8787:8787 tideway:local   # isolated container
python run.py --no-demo --db data/empty.sqlite3                                         # empty workspace
```

## Proof, not promises

<img src="docs/media/stats.svg" alt="Tideway by the numbers" width="100%">

```bash
python -m unittest discover -s tests     # full automated suite
python -m tideway.selftest               # 30-case task and attack scorecard
python scripts/evaluate_treasury.py      # 13-week reconciliation, health score, passport checks
python scripts/evaluate_portfolio.py     # portfolio radar backtest
```

Raw results live in [`evidence/`](evidence); the [readiness index](docs/READINESS_CURRENT.md) maps every claim to its evidence.

## Documentation

| | |
|---|---|
| [Technical documentation](docs/TECHNICAL_DOCUMENTATION.md) | Architecture, algorithms and data flow |
| [Pitch deck](slides/pitch-lean.pdf) · [Security report](docs/security-report-lean.pdf) | Submission documents |
| [Treasury hub](docs/TREASURY_HUB.md) · [Portfolio radar](docs/PORTFOLIO_RADAR.md) | Lender-grade features, formulas and limits |
| [Decision lab](docs/DECISION_LAB.md) · [Owner view](docs/OWNER_VIEW.md) | Decision support in depth |
| [Model card](docs/MODEL_CARD.md) · [GPU training](docs/TIDELM_CUDA.md) | Models, training and evaluation |
| [Setup on Windows and macOS](docs/SETUP_WINDOWS_MAC.md) · [Demo script](docs/DEMO_SCRIPT.md) | Running and presenting |
| [Release notes](docs/RELEASE_V15.md) | What changed most recently |

## Team

**The Last BrainCell** · Bangladesh University of Engineering and Technology (BUET)

Nafis Mohtasim Ramim · Shaharia Rahman Santo · Md. Atik Khan · Md. Ashraf Hossain Chowdhury · Khandaker Shadman Sakib Siddiquee · Md Adib Raian

## Scope

Tideway runs in a synthetic sandbox: fictional businesses and simulated counterparties, with no real bank, lender, supplier or customer connected and no real money moved. Forecasts are projections, not bank balances; scores and tiers are decision support, not credit decisions.

## License

Tideway application code is released under the [MIT License](LICENSE). Third-party models and tools keep their own licenses; see [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).
