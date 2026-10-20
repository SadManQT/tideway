# V15: lender-grade treasury, portfolio early warning and plain-language help

V15 widens Tideway from one owner's cash rescue to the people around that owner:
the finance team, the lender reviewing the business, and the bank that manages
many such businesses. It also makes every page explain itself so that anyone in
the company can use it. All data remains synthetic; no real bank, lender,
customer or supplier is connected and no real money moves.

## Treasury hub (new page)

[Feature guide](TREASURY_HUB.md) · evidence: `evidence/treasury/treasury-report.json`

- **13-week cash flow.** Weekly receipts by customer, supplier bills, payroll,
  other spend, net flow, closing and lowest cash against the reserve, for the
  scheduled, likely (TidePay) and stress scenarios. Buckets are taken directly
  from the projection engine; the server refuses to answer if week-13 closing cash
  or the daily minimum disagrees with it. CSV export (`/api/export?kind=twcf`).
- **Working-capital health score.** Six weighted components (collection speed,
  overdue share, customer concentration, runway, reserve coverage, simulated
  breach risk), each with its formula shown, plus the three data-based changes
  that would raise the score most. The weights are Tideway's documented choices,
  not validated against outcomes. Synthetic demo scores: Shapla 41, Lotus 58,
  Harbourline 26.
- **Payment-integrity scan.** Possible duplicate bills, split-under-threshold
  patterns, payee amount outliers (median/MAD), changed bank details and
  look-alike payees, and round amounts. Advisory only: it blocks, approves and
  executes nothing; existing fraud blocks stay authoritative. A clearly labelled
  in-memory synthetic sample (never saved) finds 6/6 planted anomalies with no
  false positives; that sample was written alongside the rules, so this checks
  implementation behaviour, not real-world accuracy.
- **Verifiable credit passport.** A signed (HMAC-SHA256 under a sub-key derived
  from the store key, so it can never verify as a mandate), 30-day summary a
  business can hand a lender. Issuing needs an owner or accountant and a PIN and
  is written to the audit chain. Verification reports valid, signature mismatch,
  wrong business, expired or malformed; a tamper drill shows any edit failing.
  Each passport also carries an Ed25519 public-key signature (pure-Python RFC 8032,
  verified against the RFC test vector), so a lender can verify it offline with
  `scripts/verify_passport.py` and the issuer's public key. The signing key is
  demo-grade and passports cannot be revoked before expiry.

## Portfolio radar (new page)

[Feature guide](PORTFOLIO_RADAR.md) · evidence: `evidence/portfolio/portfolio-report.json`

An early-warning view for banks, lenders and large buyers over a seeded synthetic
portfolio of 60 SMEs (BDT, CNY, INR, SGD; five sectors). Per SME: breach
probability from 400 TidePay-driven simulated futures, 14/30-day risk, expected
and worst-5% shortfall, the main driver, a red/amber/green tier and advisory
text. Portfolio totals are kept per currency (never summed across currencies).
A shock control re-runs the portfolio with extra customer delay and shows the
tier-migration matrix.

Backtest on 600 synthetic SMEs (10 portfolios, independent realised futures):
radar AUC 0.971 (95% bootstrap interval 0.954–0.984), Brier 0.057, red-tier
precision 97% and recall 69%, versus 0.928 / 0.143 / 100% / 41% for a
scheduled-only projection and AUC 0.783 for cash ÷ payroll. Calibration is weak
in the 5–50% range (observed rates 1.5–2.2× predicted), and the realised futures
come from the same synthetic generator TidePay learned from, so these figures
are flattered. The radar never reads tenant workspaces (the module does not
import the store, service or server; a test enforces this), is not a credit
decision and has not been validated on real data. Cold call ≈1.6 s on the build PC.

## Plain-language help on every page

`web/helper.js`, `web/helper.css`, tests: `tests/test_helper_layer.py`

- A "What is this page?" card above every page: its purpose in one sentence,
  three things to do, who it is for, the signed-in role, and what is safe.
- About 40 finance and security terms (reserve floor, mandate, maker-checker,
  DSO, Monte Carlo, HMAC...) are underlined once per page and explained in one
  plain sentence on hover, focus or tap. Text inside inputs, buttons, code and
  the user's own chat messages is never altered.
- A one-minute guided tour of the navigation, Help on/off and a larger-text mode,
  remembered per browser.
- The layer makes no network requests and has no approval, execution or record
  authority; a test checks the source for API, fetch, eval and money actions.

## Clearer everyday UI

- Risk dots now read "about N in 20" and explain that they round the exact
  percentage from all simulated runs; a small non-zero risk is called out.
- Raw evaluation JSON links are labelled as downloads ("Download ... report (JSON)").
- Manual mandate-signature checking moved into a collapsed "Advanced
  verification" section with its scope stated: a valid signature does not mean
  money moved or that the mandate is active or executable.
- The Decision-lab technical JSON is readable (dark text on its light panel).
- Simple view is English-only; the assistant remains multilingual.

## TideLM trained on a consumer GPU

[Details](TIDELM_CUDA.md) · evidence: `evidence/ml-cuda/`

A PyTorch/PEFT path trains the TideLM LoRA adapter on Windows with an NVIDIA RTX
3060 Ti (7.3 minutes, 5.2 GB peak VRAM) on Qwen3-1.7B. On the full held-out
synthetic test set: exact tool plans 21.3% to 92.7%, extraction F1 0.30 to 0.99,
injection-flag accuracy 62% to 100%. A loopback-only server lets the app use it.

## Works without a model

Without any language model installed, the built-in assistant now answers the
common questions in Chinese, Spanish, French, Portuguese and Indonesian with the
same numbers as English, and the Inbox extracts draft records from bank and
mobile-money alerts with clearly labelled rules. Drafts still need confirmation.

## Pitch video

`scripts/pitch_video/` renders a narrated, captioned video of at most 4:55 from
`storyboard.json`: animated vector title scenes plus live recordings of the app
on a fresh synthetic database. Output: `dist/video/tideway-pitch.mp4`.

## Verification

Full unit suite on Windows, Python 3.11.9: 557 tests passed, 4 skipped
(`python -m unittest discover -s tests`). JavaScript syntax check: 19 files.
Self-test: 30/30. Treasury and portfolio evaluations are in their evidence files.

## Limits

Everything above runs on synthetic data. The new scores, tiers and scans are
decision support, not credit decisions or fraud determinations. Usability of the
help layer has not been measured with participants.
