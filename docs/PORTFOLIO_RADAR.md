# Portfolio radar: lender early warning across a synthetic SME portfolio

> **Synthetic only.** The radar runs on its own generated portfolio of fictional SMEs. It never reads a
> tenant workspace, it is not a credit decision or credit score, and it has not been validated on real
> SME or lender data. Every number below comes from `scripts/evaluate_portfolio.py`
> (`evidence/portfolio/portfolio-report.json`).

## Purpose

Banks, lenders and large buyers do not manage one SME; they manage thousands. Tideway's single-business
cash weather answers "will *my* cash fall below my reserve?". The portfolio radar asks the lender's
question: *which of my SMEs are most likely to breach their own reserve floor in the next 60 days, when,
why, and what should my relationship managers do first?*

Code: `tideway/portfolio.py` (engine), `web/portfolio.js` (`window.TidewayPortfolio`), tests in
`tests/test_portfolio.py`, evaluation in `scripts/evaluate_portfolio.py`.

## Method

**Portfolio generation** (`generate_portfolio(n=60, seed=2026)`). Each SME gets its own seeded stream:
sector (services, wholesale, retail, manufacturing, print — the TidePay synthetic sectors), market
(BD/BDT 40%, CN/CNY 20%, SG/SGD 20%, IN/INR 20%), monthly payroll (lognormal, USD 1.5k–45k scaled by
Tideway's illustrative currency table), a latent health factor that drives billing-to-payroll and
opening-cash-to-payroll multiples, a reserve floor of 15–45% of payroll, payroll on the 25th, month-end
or semi-monthly, rent, utilities and two or three suppliers. Each SME has 3–8 customers with a latent
payment personality (prompt / typical / slow / distressed, from `tideway/ml/synth.py`), payment terms,
a drift trend and an invoice frequency. Invoices are issued from June 2026; those paid before the
1 October 2026 opening date become settled history, the rest are open (overdue or confirmed). Confirmed
billing runs to day 30 of the 60-day horizon. Every record passes the normal `tideway.domain` validators.

**Radar** (`radar(shock=None, seed=2026)`). For each SME: cash events from `projection.build_events`,
lateness probabilities for each open invoice from TidePay (`analytics.tidepay_predictions`), then a
seeded Monte Carlo with 400 futures per SME. The sampling rule is the app's own: one shared draw per
customer per future, overdue invoices conditioned on still being unpaid, all bills fixed. A unit test
checks that the radar's breach probability equals `analytics.monte_carlo` exactly at zero shock for the
same seed and run count. Per SME the radar reports:

| Field | Definition |
|---|---|
| `breach_probability` | Share of futures where cash falls below the SME's reserve floor on any day in 60 days |
| `p_breach_14d`, `p_breach_30d` | Share of futures whose first breach is by day 14 / day 30 |
| `days_to_breach` | Median first-breach day among the futures that breach |
| `expected_shortfall_minor` | Mean reserve shortfall over all futures (in the SME's own currency) |
| `worst_shortfall_minor` | 95th percentile of the shortfall |
| `top_driver` | `structural` if the scheduled projection breaches even with every invoice paid on its due date; otherwise the customer whose late invoices (due before the breach day, arrived after it) carry the most cash across breaching futures |
| `tier` | **red** if breach probability ≥ 50%, **amber** if ≥ 15%, otherwise **green** (the same cut-offs as the app's Storm / Unsettled cash weather) |
| `intervention` | Advisory text only (`executable: false`): urgent relationship-manager call, RM review, MOCK invoice-financing comparison, weekly monitoring with reminders, or no action |

Aggregates: count per tier, expected shortfall **per currency** (never summed across currencies), SMEs
at risk within 14 / 30 days (P(first breach by that day) ≥ 15%), mean breach probability, and
sector × tier and currency × tier counts.

**Macro stress.** `{"customer_delay_days": 0–60, "sector": "all" | one sector}` makes every open customer
payment (optionally only for one sector's SMEs) arrive N days later than it otherwise would. The stressed
run reuses the baseline's random draws (common random numbers), so a delay can never lower any SME's
breach probability; the tests check this. Output: tier-migration matrix (before → after), newly at-risk
SMEs and stressed aggregates.

## Measured results (seed 2026, 60 SMEs, 400 futures each)

Baseline: **14 red, 10 amber, 36 green**; 9 SMEs at risk within 14 days, 17 within 30 days; mean breach
probability 26.9%.

| Stress | Red / amber / green after | Moved to a worse tier | Mean breach probability |
|---|---|---|---|
| +5 days, all sectors | 23 / 10 / 27 | 17 | 26.9% → 38.9% |
| +15 days, all sectors | 39 / 9 / 12 | 34 | 26.9% → 68.2% |
| +30 days, all sectors | 58 / 0 / 2 | 44 | 26.9% → 95.0% |
| +30 days, retail only | 23 / 8 / 29 | 9 | 26.9% → 41.8% |
| +30 days, manufacturing only | 28 / 9 / 23 | 14 | 26.9% → 48.4% |

The portfolio is very sensitive to across-the-board delays because the ledgers carry about one month of
cash and include no new billing after day 30; this is a property of the synthetic portfolio, not a
forecast for any real market.

**Run-count stability.** Against 2,000 futures per SME, 400 futures change breach probabilities by
0.85 percentage points on average (maximum 4.45 points) and agree on 98.3% of tiers (59/60).

**Timing** (this Windows PC, Python 3.11.9, median of 3; see `timings` in the report):

| Call | Median | Max |
|---|---|---|
| Cold baseline radar (generate + validate 60 ledgers, TidePay, 24,000 futures, backtest) | 1,622 ms | 1,646 ms |
| Cold radar with an all-sector shock (baseline + stressed run, worst case) | 2,615 ms | 2,662 ms |
| New all-sector shock, baseline already cached | 847 ms | 900 ms |
| New single-sector shock, baseline already cached | 190 ms | 200 ms |
| Repeated identical call (deterministic result cache) | 0.8 ms | 0.9 ms |

All measured calls are under the 3-second target on this PC; the worst case leaves about 0.4 s of
headroom, so a slower machine may exceed it on the first stressed call. Each call is deterministic, so
the server can warm the cache once at start-up.

## Backtest (the credibility number)

**Method.** For every SME one realised 60-day future is drawn from the *generative* payment process
(customer personality, invoice size relative to the customer's usual order, month-end, terms, trend and
heavy-tail delays), with an independent seed, never from the radar's own draws. Open invoices are
conditioned on being unpaid at the opening date by rejection sampling (8 invoice draws across the 600 pooled SMEs fell back
to "current lateness plus 0–14 days" after 200 tries). Each realised future also has a 15% chance of an
unexpected expense of 10–40% of monthly payroll, which the radar cannot see. An SME "actually breached"
if realised cash went below its reserve floor on any day.

Scores: ROC AUC (ranking), Brier score (probability accuracy) and precision/recall of the red tier.
Baselines: (a) **scheduled projection** — the deterministic ledger with every invoice paid on its due
date; score = (reserve − scheduled minimum cash) per month of payroll; its "red" = a scheduled breach;
its Brier uses the 0/1 forecast; (b) **opening cash ÷ monthly payroll** (AUC only).

**Pooled: 10 independent portfolios (seeds 1–10), 600 SMEs, 146 breached (24.3%).**
Bootstrap 95% intervals from 1,000 resamples.

| Metric | Portfolio radar | Scheduled projection | Cash ÷ payroll |
|---|---|---|---|
| ROC AUC | **0.971** (0.954–0.984) | 0.928 (0.903–0.950) | 0.783 (0.745–0.821) |
| Brier score (base-rate reference 0.184) | **0.057** (0.044–0.071) | 0.143 (0.117–0.172) | — |
| Red-tier precision | 97.1% (101/104) | 100% (60/60) | — |
| Red-tier recall | **69.2%** (101/146) | 41.1% (60/146) | — |

AUC gain over the scheduled projection: 0.043 (95% interval 0.024–0.063).

**Default portfolio shown in the UI (seed 2026): 18 of 60 breached.** Radar AUC 0.951, Brier 0.081,
red precision 85.7% (12/14), recall 66.7% (12/18). Scheduled projection AUC 0.901, Brier 0.217,
precision 100% (5/5), recall 27.8% (5/18). Cash ÷ payroll AUC 0.728. Base-rate Brier 0.210.

**Calibration (pooled).** The radar under-estimates risk in the middle of the range:

| Predicted range | SMEs | Mean predicted | Observed breach rate |
|---|---|---|---|
| 0–5% | 375 | 0.7% | 1.6% |
| 5–15% | 61 | 8.9% | 19.7% |
| 15–50% | 60 | 30.8% | 45.0% |
| 50–90% | 32 | 69.4% | 90.6% |
| 90–100% | 72 | 99.7% | 100% |

Honest reading: the radar ranks SMEs better than the deterministic projection and much better than a
cash ratio, and it finds many more of the eventual breaches in its red tier, at a small precision cost
(three false alarms in 104 versus none in 60). It is not well calibrated: for predictions between 5% and 50%,
observed breach rates are about 1.5–2.2× the predicted probability, because the realised futures contain independent
per-invoice noise and unexpected costs that the radar does not model. A lender should read the
probability as a ranking signal, not a literal default rate. The realised futures come from the same
generative family that TidePay was trained on, which flatters the radar; no stronger baseline (for
example a deterministic TidePay "likely" projection) was evaluated.

## Security and privacy design

* **No tenant data.** `tideway/portfolio.py` imports only domain validators, projection, analytics,
  the TidePay model and the synthetic generator. It does not import the store, service, server, agent
  or `sqlite3`; a test parses its imports and runs it in a fresh interpreter to confirm none of those
  modules are loaded. SME ids are `pf-sme-NNN` and never collide with workspace ids.
* **Labelled.** Every response and row carries `synthetic: true`, a visible SYNTHETIC label, and
  `security: {tenant_data_read: false, store_access: false, executable_actions: false,
  credit_decision: false}`.
* **Advisory only.** Interventions are text with `executable: false`; financing is labelled MOCK.
  Nothing in the radar can approve, execute, contact a customer or change a ledger.
* **Bounded inputs.** `shock_days` must be a whole number 0–60; `sector` is whitelisted; unknown or
  repeated query parameters are rejected with `ValidationError`. Results are deterministic and cached
  (LRU, 64 entries), so repeated requests cost under a millisecond.
* **UI.** All text is escaped with the app's `esc` helper; amounts stay in each SME's own currency and
  are excluded from display-currency conversion.

## Integration

Intended server route: `GET /api/portfolio/radar?shock_days=0-60&sector=all|services|wholesale|retail|manufacturing|print`,
handled by `portfolio.radar_from_query(parse_qs(query))`, for any signed-in operator. It needs no
business scoping because it never touches tenant data. The UI module is `window.TidewayPortfolio`
(`render`, `action`, `bind`, `reset`, `validateCurrency`) with `data-action="portfolio-…"` buttons, the
same contract as the Decision lab. Bars are SVG and heat cells use CSS classes, so the page works under
the app's `style-src 'self'` Content-Security-Policy.

## Limits

* Synthetic portfolio only; not validated on real SME, bank or lender data.
* Not a credit decision, credit score or underwriting tool; interventions are suggestions for people.
* Only customer payment timing is uncertain in the radar; costs, payroll and new sales are fixed.
  Ledgers include confirmed billing to day 30, so late-horizon risk is conservative.
* The probability is under-calibrated in the backtest (above); treat it as a ranking.
* The backtest's realised futures share TidePay's synthetic generative family (in-distribution).
* Determinism holds for a given Python version (the generator uses `random` distributions beyond
  `random()`).

## Reproduce

```bash
python -m unittest tests.test_portfolio -v
python scripts/evaluate_portfolio.py      # writes evidence/portfolio/portfolio-report.json (~40 s)
```
