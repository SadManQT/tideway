# Tideway: demo recording script (4:40, limit 5:00)

Record the running app at <http://127.0.0.1:8787> with English narration. Start from a fresh workspace (delete `data/tideway.sqlite3`, run `python3 run.py`). Say once, early, that every record is synthetic and no real money moves. `demo/` holds no final recording yet; **re-record this script** before submission.

Sign-in PINs (synthetic): owner Nadia `2468`, accountant Imran `1357`, viewer Guest `0000`.

| Time | Screen | Narration |
|---|---|---|
| 0:00–0:25 | Sign in as Nadia. Overview of Shapla Services: cash weather **Storm** | "Tideway is an approval-gated cash-flow rescue agent for small businesses. This is a synthetic BDT sandbox: no bank, no real money. Payroll is coming and the schedule is short." |
| 0:25–0:55 | Cash projection, scenario lines, "N of 20 futures fall short" | "Scheduled cash dips to minus BDT 10,000 on 31 October: BDT 30,000 under the reserve. Customer payment habits make it worse, and a seeded Monte Carlo of 1,000 runs shows how often the reserve breaks." |
| 0:55–1:15 | Customer payment behaviour card | "Each customer's expected delay blends their own history with the business average, so one lucky payment doesn't make anyone look reliable." |
| 1:15–1:50 | Rescue view: **Run the rescue agent** | "The agent runs visible steps: read, profile, project, simulate, check security, compare plans. It has read and propose tools only; there is no approve or execute tool." |
| 1:50–2:20 | Recommended bundle: actions, cost, risk before and after, mock financing comparison | "An exact search checks every combination of deferrals and early-payment offers, keeps only those that hold the reserve every day and protect payroll, then re-tests the best with Monte Carlo. Financing is a labelled mock comparison and never executes." |
| 2:20–2:55 | **Review and approve** as Nadia: PIN, type the exposure amount; sign in as Imran, approve; mandate issued | "Above the threshold two people approve, with PIN step-up and a typed amount. The result is an HMAC-signed mandate: scoped, expiring, modelled on the AP2 idea." |
| 2:55–3:25 | **Send requests to counterparties**; show accept, counter-offer, reject on Lotus Print (switch business); **Turn the counter-offer into a new proposal** | "Simulated suppliers and customers answer. A counter-offer is a new proposal and needs fresh approval. A refusal triggers a re-plan." |
| 3:25–3:50 | **Execute once in the sandbox**; receipt with state hashes and read-back; cash weather improves | "Execution is idempotent and verified by read-back. No money moved; this is a sandbox." |
| 3:50–4:20 | Switch to Meghna Traders; Records show quarantined and blocked bills; Assistant: "Check security" | "A changed bank account, a look-alike payee and a poisoned bill with hidden characters are blocked. The text never reaches a model. Here no safe plan exists, so Tideway says so and escalates." |
| 4:20–4:40 | Security: **Run self-test** (30/30), Evidence: **Tamper drill**, **Pause the agent now** | "Thirty cases: five tasks, twenty-five attacks, with a hijacked model and a rubber-stamp human assumed. The audit chain is hash-linked and witnessed; the drill shows an edit being caught. One click pauses the agent." |

## Backup path

If the app fails, play the recorded video and say it is a recording. Keep `evidence/screens/` (15 PNGs) as a fallback. The reset is "delete the database file and restart".

## Do not show

`.env`, keys, terminal paths with personal names, or any real customer data. Do not describe the recording as a live production run, and do not describe the optional LLM mode as measured.
