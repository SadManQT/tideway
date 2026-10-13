# Probaho — Demo recording plan

Target length: **4:30–4:55**, below the roadmap’s five-minute maximum. Record the running app, not only screenshots. Use English narration. Identify every record as synthetic unless a separately consented pilot is actually included.

`demo/demo.mp4` is currently a generated **visual rehearsal** from isolated screenshots. It is useful for timing and review, but it is not a final live/narrated execution recording and must not be submitted as such without team review and a real running-app recording.

## Recording sequence

| Time | Screen action | Narration |
|---|---|---|
| 0:00–0:25 | Cash gap overview for Shapla Services | “Probaho is an approval-gated SME cash-flow recovery copilot. This is a synthetic BDT sandbox, not a bank balance.” |
| 0:25–0:55 | Show opening cash, base closing cash, reserve floor, and BDT 30,000 shortfall | “The figures are deterministic and linked to source records: BDT 120,000 opening cash, BDT 80,000 payroll, BDT 70,000 supplier bill, and BDT 20,000 confirmed inflow.” |
| 0:55–1:20 | Open source-linked records and timeline | “The cash gap is explained by dated transactions, an invoice, and a supplier bill. A reminder is never treated as a collection.” |
| 1:20–1:45 | Recovery plans; compare reminder, supplier reschedule, mock financing | “Probaho compares options. The supplier plan defers only BDT 40,000 to a later synthetic date. Financing alternatives show principal, fee, repayment, and term, but cannot execute.” |
| 1:45–2:15 | Open supplier plan review | “Before approval, we show the payee, bill ID, amount, original due date, deferred date, target, assumptions, and constraints.” |
| 2:15–2:40 | Click **Approve plan** | “Approval is a separate human action. The model cannot approve.” |
| 2:40–3:05 | Show consent panel; click **Simulate supplier acceptance** | “This is an explicit local simulation of supplier acceptance, not a real supplier response. Without it, execution remains blocked.” |
| 3:05–3:40 | Click **Execute approved action** | “Execution changes only the synthetic schedule. There is no bank call and no instant cash movement.” |
| 3:40–4:05 | Show receipt, before/after state, projections, and read-back | “The receipt binds the action to its approval, snapshot, policy, and idempotency key. The post-commit state is read back from the sandbox.” |
| 4:05–4:25 | Open Activity & evidence and export | “Every proposal, approval, consent, execution, and rejection carries a permission and hash-chain receipt.” |
| 4:25–4:45 | Open Assistant and ask “What is the cash gap?” | “Offline mode is labelled Local demo. The assistant can read and propose, but cannot approve or execute.” |
| 4:45–4:55 | Reset sandbox | “Reset removes the accepted synthetic schedule while preserving records and execution history.” |

## Backup path

If the live app or provider is unavailable, use the recorded local demo only and say so. Keep a screenshot/PDF backup of the overview, plan review, receipt, and evidence pages. Never call offline tool receipts live-model evidence.

## Do not show

- `.env`, API keys, tokens, private CSV files, passports, or personal terminal paths.
- A real bank account, real supplier, real loan decision, or unverified user-study claim.
- A reminder as collected cash.
- Mock financing as an executable action.
- A generated receipt without the corresponding actual sandbox state.
