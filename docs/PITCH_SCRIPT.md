# Tideway: pitch script (about 9 minutes, limit 10)

Slides match `slides/pitch.pdf` (12 slides; every number on them is read from `evidence/` when the deck is built). Replace team details before presenting. Say once that all data is synthetic.

## 1. Tideway (slide 1, 0:00–0:30)
"Tideway helps a small business never miss payroll again. It is on-device AI that predicts which customers will pay late, plans a cash rescue before the gap hits, and acts only with the owner's approval."

## 2. The moment that matters (slide 2, 0:30–1:10)
"Small businesses get paid late and still have to pay on time, and the gap lands on payroll day. The owner needs three answers fast: will I make payroll, who will pay late, and what do I do now? And an AI that helps must never be able to move money on its own."

## 3. See it coming (slide 3, 1:10–1:50)
"Shapla Services: BDT 120,000 in the bank, BDT 80,000 payroll, a BDT 70,000 supplier bill, BDT 20,000 coming in, a BDT 20,000 reserve. The schedule says minus BDT 10,000 on 31 October. These are exact integer calculations linked to source records, shown as cash weather with 1,000 simulated futures."

## 4. TidePay (slide 4, 1:50–2:40)
"Whether a customer pays late is the uncertainty that matters, so we built our own model for it. TidePay is trained with federated learning across forty businesses with secure aggregation: nobody shares raw invoices, and the server only sees masked updates. It beats the old rule clearly, and it helps small businesses most, because they learn from everyone without exposing anyone."

## 5. TideLM (slide 5, 2:40–3:40)
"For the conversation we did not rent an API. We fine-tuned our own model, TideLM, on a laptop: Qwen3-4B with a LoRA adapter trained on our own data. On a held-out test with company names it never saw, it went from the base model's numbers to ours on the slide: plans with every argument right, intent, reading records from bank and mobile-money messages, and catching hidden instructions. It speaks eight languages and runs on the owner's computer, so their books never leave it."

## 6. Plan, approve, execute (slides 6–7, 3:40–5:00)
"An exact optimiser searches deferrals and early-payment offers, keeps only plans that hold the reserve every day with payroll funded, and explains why the cheaper option is too risky. A person approves with a PIN; big amounts need two people and a typed amount. That issues a signed, expiring mandate bound to exactly these actions. Simulated counterparties accept, counter or refuse, and execution happens once, with read-back."

## 7. Live demo (5:00–7:00)
Run the demo script highlights: landing page and demo sign-in, cash weather, ask in Chinese or Spanish, rescue and approval, Harbourline fraud blocks and the honest "no safe plan".

## 8. Security (slide 9, 7:00–8:00)
"We assume the worst: a fully hijacked model and a rubber-stamp human. The model has no approve, pay or write tool; its plans pass a typed validator; a forbidden tool trips a circuit breaker. Injection and changed-bank-details screening work in eight languages. The audit log is hash-chained with a witness. Every attack in our suite is blocked; that is evidence for those cases, not proof."

## 9. A product, with evidence and honest limits (slides 10–12, 8:00–9:00)
"It is built as a product: sign up a business in any of 29 currencies, invite your accountant with a one-time code, and see which customer could hurt your cash most. Everything is reproducible with one command. Limits: synthetic data, simulated counterparties, demo-grade keys, no user study yet. Next: consented SME pilots, a real bank rail behind the same mandate, and federated TidePay across real users."

## Likely judge questions
- **Why train your own model instead of calling an API?** Privacy (books never leave the device), cost (no per-call fee), control (a narrow, tested skill set) and measurable gains on our task; the base-vs-tuned table is in `evidence/ml/`.
- **What if the AI is wrong?** It cannot act. Figures come from tools; plans are validated; names are resolved against the ledger; every action needs a signed mandate approved by people.
- **Isn't 4B too small?** It only has to choose tools and fill arguments, not reason about money; the arithmetic is deterministic code.
- **How is TidePay private?** Federated averaging with pairwise masks that cancel in the sum; the server never sees one business's update.
- **Why synthetic data?** Reproducibility and attack coverage; we report no real-user results.
- **Is the mandate AP2?** Modelled on the idea; not an implementation of the AP2 specification.
- **Who pays?** Hypothesis: small businesses or their accountants, per seat; plans shown are illustrative.
- **Why no real bank?** The rules accept sandbox evidence; the ISO 20022 pain.001 draft shows the adapter boundary and is never sent.
