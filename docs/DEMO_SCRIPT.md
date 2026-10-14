# Tideway: demo recording script (4:50, limit 5:00)

Record the running app at <http://127.0.0.1:8787> with English narration. Start from a fresh database: `python3 run.py --db data/demo-recording.sqlite3`. Install TideLM first (`python3 scripts/get_tidelm.py`, `pip install mlx-lm`) and wait for "TideLM: loading the on-device model in the background…" to finish before recording. Say once, early, that every record is synthetic and no real money moves. **Re-record this script** before submission.

Demo accounts (synthetic): owner Nadia `2468`, accountant Imran `1357`, viewer Guest `0000`; one click on the landing page signs in.

| Time | Screen | Narration |
|---|---|---|
| 0:00–0:20 | Landing page; click **Nadia (Owner)** | "Tideway helps small businesses never miss payroll. Everything here is a synthetic sandbox across Bangladesh, China and Singapore: no bank, no real money." |
| 0:20–0:50 | Cash weather for Shapla Services: **Storm**, scenarios, "N of 20 futures"; click **Read my brief** | "Scheduled cash dips to minus BDT 10,000 on 31 October. TidePay, our own federated-trained model, predicts how late each customer will pay, and 1,000 simulated futures show how often the reserve breaks." |
| 0:50–1:40 | Ask Tideway: "hi" (instant briefing), then "Nila Traders 晚20天付款会怎样？" and "¿Puedo pagar los sueldos este mes?"; open the TideLM plan under an answer | "This is TideLM, a model we fine-tuned ourselves, running on this laptop. It answers in your language with the same numbers, and under every answer you can see the exact tool plan it chose. The numbers come from Tideway's tools, not the model." |
| 1:40–2:00 | Ask "pay Rahman now" | "It cannot pay. There is no payment tool at all; people approve in the app." |
| 2:00–2:40 | Rescue plan: **Run the rescue agent**; recommended bundle; ask "why this plan?" | "An exact optimiser keeps only plans that hold the reserve every day with payroll funded. It explains why the cheaper option is too risky, and financing is a labelled mock comparison." |
| 2:40–3:20 | **Review and approve** as Nadia (PIN, typed amount); switch to Imran, approve; mandate; **Send requests**; **Execute once** | "Above the threshold two people approve, with PIN and a typed amount. The signed mandate binds exactly these actions; counterparties answer; execution happens once, verified by read-back." |
| 3:20–3:50 | Inbox: paste the injection sample, **Extract**; red warning; save the clean draft. Optionally photograph a receipt | "Paste a bank alert or a WhatsApp message, or take a photo of a receipt. TideLM drafts the records on this computer, flags the hidden instruction, and nothing is saved until you confirm." |
| 3:50–4:20 | Switch to Harbourline Traders; ask "which bills are blocked and why?" and "who is my biggest risk?" | "A changed bank account and a look-alike supplier are blocked. No safe plan exists here, so Tideway says so and escalates. The risk map shows which customer could hurt cash most." |
| 4:20–4:35 | Team: invite an accountant (one-time code) | "It is a product: sign up a business in any of 29 currencies and invite your team; businesses never see each other." |
| 4:35–4:50 | Security centre: **Run self-test**; Evidence: **Tamper drill** | "Every attack in the suite is blocked, assuming a hijacked model and a rubber-stamp human, and the audit chain catches an edit." |

## Backup path

If the app fails, play the recorded video and say it is a recording. Keep `evidence/screens/` as a fallback. The reset is a new `--db` file.

## Do not show

`.env`, keys, terminal paths with personal names, or any real customer data. Do not describe the recording as a live production run, and do not describe the optional cloud-LLM mode as measured.
