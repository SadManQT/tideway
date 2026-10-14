# Tideway: pitch script (about 9 minutes, limit 10)

Slides match `slides/pitch.pdf`. Replace team details before presenting. Every number below is from the synthetic fixtures or the self-test; say so.

## 1. Problem (0:00–0:50)
"A small business does not need another dashboard. When payroll is days away and cash is short, the owner needs to know: what can I safely defer, who can I ask, and what happens if my customers pay late? And an AI that answers that must never be able to move money on its own."

## 2. A concrete case (0:50–1:40)
"Shapla Services: BDT 120,000 in the bank, BDT 80,000 payroll, a BDT 70,000 supplier bill, BDT 20,000 coming in, and a BDT 20,000 reserve. The schedule says cash falls to minus BDT 10,000 on 31 October, BDT 30,000 short of the reserve. These figures are exact integer arithmetic linked to source records, not a model's guess."

## 3. What Tideway does (1:40–3:30)
"It profiles each customer's payment behaviour with credibility weighting, projects three scenarios with a 14-day look-ahead, and runs a seeded 1,000-run Monte Carlo for the chance of breaching the reserve. An exact optimiser then searches supplier deferrals and early-payment discounts, keeps only bundles that hold the reserve every day and protect payroll, and recommends the cheapest one whose simulated risk is acceptable. Early-payment discounts are priced as an annual rate: two percent for twenty days is about 37% APR. Financing is a labelled mock comparison."

## 4. Negotiate and decide (3:30–4:30)
"Simulated suppliers and customers accept, counter or refuse. A counter-offer becomes a new proposal; a refusal triggers a re-plan. A human approves with a PIN step-up; high-value bundles need two people and a typed amount. That issues a signed mandate, modelled on the AP2 mandate idea, and execution happens once, with read-back."

## 5. Live demo (4:30–6:30)
Run the demo script highlights: Shapla rescue and approval, Lotus counter-offer, Meghna blocks and honest failure.

## 6. Security (6:30–8:00)
"We assume the worst: a fully hijacked model and a rubber-stamp human. The model has no approve or execute tool, sees only pseudonyms, and cannot be the weak link. Hidden Unicode is stripped, injected instructions are quarantined, changed bank details and look-alike payees block the bill, and payee verification is owner-only by callback with separation of duties. A kill switch and a circuit breaker stop the agent. The audit log is hash-chained with an independent witness, so edits and truncation are detected. Our 30-case suite maps to OWASP LLM and Agentic IDs; all pass, and that is evidence for those cases, not proof."

## 7. Honest limits and what is different (8:00–9:00)
"This is a synthetic sandbox with simulated counterparties; PINs and keys are demo-grade; we have not measured a live model or run a user study. We are not the first cash-flow assistant; incumbents offer forecasting and reminders. Our contribution is a complete, replayable loop from gap to safe action, with enforcement outside the model. Next: baseline comparison, consented SME interviews, a real rail adapter behind the same mandate."

## Likely judge questions
- **How is this different from a general chatbot?** Exact projection, optimiser, enforcement and state outside the model; a baseline comparison is planned, not yet run.
- **What if the AI is wrong?** It cannot act: figures come from tools, answers are grounded-checked, and execution needs a signed mandate.
- **Why synthetic data?** Reproducibility and attack coverage; we report no real-user results.
- **Is the mandate AP2?** Modelled on the idea; not an implementation of the AP2 specification.
- **Who pays?** Hypothesis: small businesses or their accountants; unvalidated.
- **Why no real bank?** The rules accept sandbox evidence; the ISO 20022 pain.001 draft shows the adapter boundary and is never sent.
