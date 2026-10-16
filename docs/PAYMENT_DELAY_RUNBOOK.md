# Live linked payment-delay demonstration

Use synthetic Shapla Services, the native BDT display, and target 31 October 2026. The delay deliberately moves Bay Logistics beyond the 14 November look-ahead. The planner is unchanged and no counterparty response is forced.

## Start fresh without deleting evidence

Choose a database filename that has never been used:

```bash
python3 run.py --db data/contest-rehearsal-01.sqlite3 --port 8788
```

Open http://127.0.0.1:8788. A new filename starts from the fixtures; do not overwrite another database. For an automatic rehearsal that refuses existing database paths:

```bash
python3 scripts/demo_payment_delay.py
python3 scripts/demo_payment_delay.py --db data/rehearsal-new.sqlite3 --out evidence/upgrade-v1/rehearsal-new.json
node scripts/capture_screens.mjs --test-payment-delay --out tmp/delay-browser
```

## Live sequence (about four minutes)

1. Sign in as Imran (`1357`), select Shapla Services, and run the rescue agent. Describe the trace as deterministic orchestration. Scheduled minimum is BDT -10,000; likely minimum BDT -42,000; likely reserve shortfall BDT 62,000. The original recommendation defers BDT 60,000 of Rahman's bill to 14 November and offers Nila 1% for early payment. Read cost and simulated risk from the actual plan.
2. Give Imran's approval through the Review dialog, enter the exact displayed exposure and his PIN. Sign in as Nadia (`2468`) and supply the second approval. Stop at the newly signed mandate, before execution.
3. Open **What-if**. Its sliders remain read-only. In the separate **Demonstrate a real payment delay** panel, select Bay Logistics, set **15 November 2026**, enter Nadia's PIN, check the explicit confirmation, and press **Apply payment delay to demo ledger**.
4. Read the calculated before/after table and changed snapshot. Likely minimum becomes BDT -57,000, reserve shortfall BDT 77,000. Both original and changed states already have 100% reserve-breach risk; do not describe this as a risk-percentage increase. Click **Check old mandate is blocked**. It must say the old mandate is invalidated. The audit retains both old approvals and the delay event.
5. Open Rescue, run a fresh proposal. It now offers early payment to Bay Logistics and Nila instead of relying on the supplier deferral. Give both ordinary approvals again. Send requests: Bay's simulated 1.5% counter-offer replaces the proposed 1%. Turn that counter into a new proposal; review and obtain fresh approvals again.
6. Send requests for the approved counter terms, execute once, and inspect the verified read-back receipt. A retry with the same execution key returns the same receipt. Compare actual plan cost/risk and source actions, not a rehearsed invented number.

## Safety and recovery

The mutation requires an owner membership, PIN, an open invoice whose source is `demo`, a synthetic business, an active policy and a current snapshot. An immediate transaction changes one date, supersedes any earlier reminder promise, preserves quarantine flags, advances the version, invalidates live proposals/mandates, and records the audit and durable request receipt together. Conflicting concurrent requests fail; exact retries replay the original receipt. The old authority never becomes usable again.

Invalid requests and simulated audit failures leave the ledger and authority unchanged. A response lost after commit can be retried with the same request id in the open tab. If records changed, reload and review. If a fixture has already been executed, start a new database for the full sequence; existing databases and evidence are not reset or erased.

The automatic rehearsal uses the validated `Application.post` workflow, normal PIN/dual approvals and actual simulated consent. The browser variant also checks desktop/mobile rendering and the stale execution HTTP refusal. Neither test invokes a real model or real payment rail. Video recording remains deferred.
