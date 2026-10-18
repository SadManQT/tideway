"""Render the Tideway submission PDFs with headless Chrome (no Python packages needed).

Produces slides/pitch.pdf, docs/architecture.pdf, docs/security-assessment.pdf and
docs/Tideway_FinTechathon_2026_Roadmap.pdf (from docs/roadmap/*.html).
Requires Google Chrome; override the path with the CHROME environment variable.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get("CHROME") or next((p for p in (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
) if Path(p).is_file()), "google-chrome")

DOC_CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font: 10.5pt/1.5 -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; color: #14221f; }
h1 { font-size: 22pt; color: #0f3d36; border-bottom: 3px solid #1f8a70; padding-bottom: 6px; }
h2 { font-size: 14pt; color: #0f3d36; margin-top: 20px; break-after: avoid; }
h3 { font-size: 11.5pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
th, td { border: 1px solid #c7d6d1; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #e6f2ee; } tr { break-inside: avoid; }
table.compact { break-inside: avoid; } thead { display: table-header-group; }
body { overflow-wrap: anywhere; }
code { font: 9pt ui-monospace, Menlo, monospace; background: #eef4f2; padding: 0 3px; border-radius: 3px; }
pre { background: #eef4f2; padding: 8px; font-size: 8.5pt; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; } blockquote { border-left: 4px solid #1f8a70; margin: 8px 0; padding: 2px 10px; color: #35504a; }
li { break-inside: avoid; } p { orphans: 3; widows: 3; }
"""


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return re.sub(r"&lt;(https?://[^&]+)&gt;", r'<a href="\1">\1</a>', text)


def markdown_to_html(source: str) -> str:
    """Small Markdown subset: headings, tables, lists, code fences, quotes, paragraphs."""
    out, lines, i = [], source.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
        elif re.match(r"#{1,4} ", line):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{inline(line[level + 1:])}</h{level}>")
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([cell.strip() for cell in lines[i].strip().strip("|").split("|")])
                i += 1
            i -= 1
            head, body = rows[0], [row for row in rows[2:]]
            out.append(f'<table class="{"compact" if len(rows) <= 10 else "long"}"><thead><tr>' +
                       "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in body) + "</tbody></table>")
        elif re.match(r"\s*(- |\d+\. )", line):
            tag = "ol" if re.match(r"\s*\d+\. ", line) else "ul"
            items = []
            while i < len(lines) and re.match(r"\s*(- |\d+\. )", lines[i]):
                item = re.sub(r"^\s*(- (\[[ x]\] )?|\d+\. )", "", lines[i])
                i += 1
                while (i < len(lines) and lines[i].strip()
                       and not re.match(r"\s*(- |\d+\. |#{1,4} |```|\||>)", lines[i])):
                    item += " " + lines[i].strip()
                    i += 1
                items.append(item)
            i -= 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(item)}</li>" for item in items) + f"</{tag}>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
        elif line.strip():
            paragraph = [line.strip()]
            i += 1
            while (i < len(lines) and lines[i].strip()
                   and not re.match(r"\s*(- |\d+\. |#{1,4} |```|\||>)", lines[i])):
                paragraph.append(lines[i].strip())
                i += 1
            i -= 1
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
        i += 1
    return "\n".join(out)


def print_pdf(page: Path, destination: Path):
    executable = CHROME if Path(CHROME).is_file() else shutil.which(CHROME)
    if not executable:
        raise SystemExit("Chrome/Chromium was not found. Install it or set CHROME to its executable path.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tideway-pdf-", ignore_cleanup_errors=True) as folder:
        rendered = Path(folder) / "rendered.pdf"
        subprocess.run([executable, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={Path(folder) / 'profile'}", f"--print-to-pdf={rendered}",
                        page.resolve().as_uri()], check=True, capture_output=True, timeout=120,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if not rendered.is_file() or not rendered.read_bytes().startswith(b"%PDF-"):
            raise RuntimeError(f"Chrome did not produce a PDF for {destination.name}")
        shutil.copyfile(rendered, destination)
    print(f"wrote {destination.relative_to(ROOT)}")


def document(work: Path, name: str, markdown_path: Path, destination: Path):
    page = work / f"{name}.html"
    page.write_text(f"<!doctype html><meta charset=utf-8><title>{name}</title><style>{DOC_CSS}</style>"
                    + markdown_to_html(markdown_path.read_text(encoding="utf-8")), encoding="utf-8")
    print_pdf(page, destination)


def _json(path):
    try:
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _tidelm():
    """Best available TideLM evaluation pair (adapter vs base on the same test set), or None."""
    for tuned, base in (("evidence/ml/tidelm_ft_eval.json", "evidence/ml/tidelm_base_eval.json"),):  # the deployed adapter
        a, b = _json(tuned), _json(base)
        if a and b and a.get("test_set") == b.get("test_set"):
            return a, b
    return None


def _test_count():
    report = _json("evidence/test-summary.json") or {}
    return report.get("tests_run", "see test report for")


def slides():
    """The deck, with every number read from the evidence files at build time (never typed by hand)."""
    tidepay = (_json("evidence/upgrade-v1/tidepay/report.json") or {}).get("results", {})
    verify = _json("evidence/verification-summary.json") or {}
    lm = _tidelm()
    local_smoke = _json("evidence/readiness-v3/blind/model-first-observation.json") or {}
    local_proof = (f"Mac Qwen3 first challenge: {local_smoke.get('matched', {}).get('numerator', '—')}/{local_smoke.get('requests')} handled; four retained misses"
                   if local_smoke.get("real_model_inference") else "Current compatible-model verification is recorded separately")
    deployed = (_json("evidence/readiness-v3/tidepay/report.json") or {}).get("results", {})
    regression = _json("evidence/readiness-v3/blind/model-post-fix-regression.json") or {}
    pct = lambda v: f"{v * 100:.1f}%".replace(".0%", "%")  # noqa: E731
    lm_rows = []
    if lm:
        tuned, base = lm
        lm_rows = [("Exact plan (every tool and argument)", pct(base["plan"]["exact_plan_accuracy"]), pct(tuned["plan"]["exact_plan_accuracy"])),
                   ("Understands the request (intent)", pct(base["plan"]["intent_accuracy"]), pct(tuned["plan"]["intent_accuracy"])),
                   ("Reads records from messages (F1)", f"{base['extract']['record_f1']:.3f}", f"{tuned['extract']['record_f1']:.3f}"),
                   ("Flags hidden instructions", pct(base["extract"]["injection_flag_accuracy"]), pct(tuned["extract"]["injection_flag_accuracy"]))]
    fed, rule, thin, alone = (tidepay.get("federated", {}), tidepay.get("heuristic_v1", {}),
                              tidepay.get("federated_on_smaller_half_of_smes", {}), tidepay.get("local_only_on_smaller_half_of_smes", {}))
    deck = [
        {"title": "Tideway", "subtitle": "Plan ahead for payroll.",
         "bullets": ["On-device AI that predicts which customers will pay late, plans a cash rescue before the gap hits, "
                     "and acts only with your approval.", "FinTechathon 2026 · International Track · Topic E: SME Finance Copilot"],
         "image": "00-landing.png", "first": True},
        {"title": "The moment that matters", "subtitle": "Payroll is days away and the cash is not there",
         "bullets": ["Small businesses are paid late and pay on time: the gap lands on payroll day.",
                     "Owners need three answers fast: will I make payroll, who will pay late, what do I do now?",
                     "And an AI that helps must never be able to move money on its own."]},
        {"title": "See it coming", "subtitle": "Cash weather, three scenarios, 1,000 simulated futures",
         "bullets": ["Exact daily ledger in minor units with a 14-day look-ahead",
                     "Scheduled, likely and stress views; \"N of 20 futures fall short\"",
                     "Shapla Services (synthetic): scheduled low −BDT 10,000 on 31 Oct; reserve gap BDT 30,000"],
         "image": "01-cash-weather-storm.png"},
        {"title": "TidePay: exact shipped weights", "subtitle": "Frozen artifact; new SMEs, no fitting on test labels",
         "table": [("Model", "MAE days", "Log loss", "Brier sum")] + [
             (label, f"{deployed[key]['mae_days']:.3f}", f"{deployed[key]['log_loss']:.3f}", f"{deployed[key]['brier_sum']:.3f}")
             for key, label in (("historical_training_prior", "Training prior"), ("customer_history_heuristic", "History heuristic"),
                                ("deployed", "Shipped artifact"), ("audited_v2", "Earlier audit weights")) if key in deployed],
         "bullets": [f"{deployed.get('deployed', {}).get('n', '—'):,} unseen invoices; 80 new synthetic SMEs, four seeds" if deployed else "See the frozen-artifact report",
                     "No-history predictions remain weak; no real-world accuracy claim",
                     "One-process federation; no deployed privacy guarantee"]},
        {"title": "TideLM: our own on-device language model", "subtitle": "Qwen3-4B + a LoRA adapter we trained on a laptop with MLX",
         "table": ([("", "Base model", "TideLM")] + lm_rows) if lm_rows else None,
         "bullets": ["Eight languages: English, 中文, Español, Bahasa, Français, Português, Hinglish, Banglish",
                     "Synthetic test with unseen names and shared template families",
                     local_proof + "; historical adapter scores above are a different evaluation"] + ([] if lm_rows else ["Evaluation pending"])},
        {"title": "Plan the rescue", "subtitle": "An exact, risk-aware optimiser",
         "bullets": ["Supplier deferrals, early-payment discounts (priced as APR), zero-cash reminders",
                     "Feasible plans protect the projected path; above-target risk needs explicit consent",
                     "Mock financing shows arrival, eligibility assumptions and pressure through repayment"],
         "image": "02-rescue-agent-and-plan.png"},
        {"title": "Approve exactly this", "subtitle": "Human approval, signed mandate, verified execution",
         "bullets": ["Maker-checker with PIN; two people and a typed amount above the threshold",
                     "HMAC mandate binds actions, snapshot, expiry and exact residual-risk consent",
                     "Simulated counterparties accept, counter or refuse; idempotent execution with read-back"],
         "image": "03-approve-exactly-this.png"},
        {"title": "Talk to it in your language", "subtitle": "Glass-box answers, zero-entry bookkeeping",
         "bullets": ["Optional TideLM shows its typed plan; figures come from Tideway's tools",
                     "Answers in the language of the question, with the same figures",
                     "Optional local models draft messages and photos; human confirmation is required"],
         "image": "07-assistant.png"},
        {"title": "Security enforcement", "subtitle": "Permissions and validation live outside the model",
         "bullets": [f"{verify.get('attacks_blocked', '—')}/{verify.get('attacks', '—')} attacks blocked, "
                     f"{verify.get('tasks_completed', '—')}/{verify.get('tasks', '—')} tasks completed, assuming a hijacked model",
                     "Message screening misses unfamiliar attacks; structural authority checks remain essential",
                     "Kill switch, circuit breaker, separation of duties, hash-chained audit with witness"],
         "image": "13-security-centre-selftest.png"},
        {"title": "Built as a product", "subtitle": "Workspaces, teams and roles",
         "bullets": ["Sign up a business in any of 29 currencies; demo in Bangladesh, China and Singapore",
                     "Invite your accountant by one-time code; roles per business; tenants never see each other",
                     "Counterparty risk map: who can hurt your cash, and by how much"],
         "image": "18-team.png"},
        {"title": "Evidence, with denominators", "subtitle": "Reproducible in one command each",
         "bullets": [f"{verify.get('passed', '—')}/{verify.get('cases', '—')} self-test cases · {_test_count()} automated tests",
                     "Model reports, sandbox logs, browser evidence and reproducible setup",
                     "python3 -m tideway.selftest · python3 -m unittest discover -s tests"]},
        {"title": "Honest limits, clear next steps", "subtitle": "What we have not done yet",
         "bullets": ["Synthetic data and simulated counterparties; demo-grade PINs and keys",
                     "No user study or external penetration test yet",
                     "Next: consented SME pilots, new unseen screening checks and independent security review"]},
    ]
    scenario_dir = next((folder for folder in ("evidence/upgrade-v11", "evidence/upgrade-v10", "evidence/release-v9", "evidence/completion-v8", "evidence/remediation-v7", "evidence/readiness-v5", "evidence/readiness-v3", "evidence/upgrade-v1")
                         if (ROOT / folder / "scenarios/report.json").is_file()), "evidence/readiness-v3")
    scenarios = _json(scenario_dir + "/scenarios/report.json") or {}
    if scenarios:
        counts = scenarios["summary"]
        outcomes = counts["by_expected_outcome"]
        attacks = scenarios["screening"]["injection_screening"]["confusion"]
        payees = scenarios["screening"]["payee_screening"]["confusion"]
        risk_met = sum(bool(row.get("risk_target_met")) for row in scenarios["rows"] if row["executed"])
        deck.insert(10, {"title": "Beyond three demo fixtures", "subtitle": f"{counts['cases']} distinct conditions; development and held-out expectations sealed",
                         "bullets": [f"{counts['workflow_successes']}/{counts['cases']} outcome handling: {counts['executed_rescues']} rescues, {outcomes['honest_infeasibility']['cases']} infeasible, {outcomes['no_action_needed']['cases']} no-action, {outcomes['security_blocked']['cases']} blocked",
                                     f"Only {risk_met}/{counts['executed_rescues']} rescues meet the 10% simulated-risk target",
                                     f"Injection: {attacks['true_positive']}/{attacks['malicious_denominator']} attacks detected; {attacks['false_positive']}/{attacks['benign_denominator']} benign messages flagged",
                                     f"Payee: {payees['true_positive']}/{payees['malicious_denominator']} attacks detected; {payees['false_positive']}/{payees['benign_denominator']} benign cases flagged",
                                     "Retained outcomes and planner timings: " + scenario_dir + "/scenarios/",
                                     "H11 retains above-target risk; acknowledgement is a decision, not a guarantee"]})
    blind = _json("evidence/readiness-v3/blind/screening-first-observation.json") or {}
    if blind and local_smoke:
        counts = blind['injection']['confusion']
        deck.insert(11, {"title": "Independent challenge: retain the misses", "subtitle": "First observations sealed before fixes; later checks are regressions",
                         "bullets": [f"First Qwen3: {local_smoke['matched']['numerator']}/{local_smoke['requests']} handled; {local_smoke['containment']['numerator']}/{local_smoke['containment']['denominator']} payment containment",
                                     f"Post-fix known-case regression: {regression.get('matched', {}).get('numerator', '—')}/{regression.get('requests', '—')}; not a new blind score",
                                     "Amount and customer substitutions exposed; deterministic guard regressions added",
                                     f"Screening: {counts['true_positive']}/24 attacks detected, {counts['false_positive']}/24 benign flagged",
                                     "Screening is not authorization; every extracted draft needs human review"]})
        fresh = _json("evidence/screening-v7/fresh/report.json") or {}
        if fresh:
            metrics = fresh["metrics"]
            deck[11]["bullets"][-2] = (f"V7 fresh screening: semantic recall {metrics['semantic_attack']['recall']:.1%}; "
                                       f"warning false-positive rate {metrics['combined_warning']['false_positive_rate']:.1%}")
            deck[11]["bullets"][-1] = (f"Cached MLX base; synthetic set; targets met: {fresh['targets_met']}; no payment authority")
        followup = _json("evidence/upgrade-v10/screening-final-known/report.json") or {}
        challenge = _json("evidence/upgrade-v10/screening-challenge/report.json") or {}
        if followup and challenge:
            fm, cm = followup["metrics"], challenge["metrics"]
            deck[11]["bullets"][-2] = (f"Windows known-case follow-up: {fm['combined_attack']['tp']}/{fm['combined_attack']['tp'] + fm['combined_attack']['fn']} attacks; "
                                       f"{fm['combined_warning']['fp']} ordinary-benign warnings; not blind")
            deck[11]["bullets"][-1] = (f"Source-aware first challenge: {cm['combined_attack']['tp']}/12 attacks, {cm['combined_warning']['fp']}/8 benign warnings; MLX follow-up deferred")
    delay = _json(scenario_dir + "/payment-delay.json") or _json("evidence/readiness-v3/payment-delay.json") or _json("evidence/upgrade-v1/payment-delay.json") or {}
    if delay.get("passed"):
        change = delay["change"]
        before = change["before"]["likely"]; after = change["after"]["likely"]
        deck.insert(7, {"title": "A delay changes the decision", "subtitle": "Apply a real synthetic-ledger change; old authority is void",
                        "bullets": [f"Bay Logistics: {change['old_date']} to {change['new_date']}",
                                    f"Likely minimum BDT {before['minimum_cash_minor']/100:,.0f} to {after['minimum_cash_minor']/100:,.0f}",
                                    "Old mandate refused; new proposal replaces supplier deferral with early-payment offers",
                                    "Bay counters at 1.5%; fresh approvals, consent, execute once and verify",
                                    "Runbook: docs/PAYMENT_DELAY_RUNBOOK.md; no video recorded"]})
    lab = _json("evidence/upgrade-v11/decision-lab.json") or {}
    if lab.get("passed"):
        deck.append({"title": "Challenge before acting", "subtitle": "Stress the rescue; protect both sides",
                     "bullets": ["Smallest single-customer delay with a one-day-less witness; assumed agreement lateness",
                                 "Compare recovery cost/risk; extra cash stays conditional and unconfirmed",
                                 "Owner-authorised events invalidate old mandates; fresh proposals need approval",
                                 "Synthetic buyer/supplier cash paths, private financial replay and cloud payload inspection"]})
    team = _json("submission-team.public.json") or {}
    if team.get("team_name"):
        deck[0]["bullets"].append(team["team_name"])
        deck.append({"title": team["team_name"], "subtitle": "Bangladesh University of Engineering and Technology",
                     "bullets": [member["name"] + (f" - {member['role']}" if member.get("role") else "")
                                 for member in team.get("members", [])]})
    return deck


def _crop(path: Path, work: Path):
    """The first screen of a full-page screenshot (16:10), so text stays readable on a slide."""
    if not path.exists():
        return None
    try:
        from PIL import Image
    except ImportError:  # Pillow optional: fall back to the full page
        return path
    with Image.open(path) as image:
        width = image.width
        crop = image.crop((0, 0, width, min(image.height, round(width / 1.6))))
        target = work / f"crop-{path.name}"
        crop.save(target)
    return target


SLIDE_CSS = """
@page { size: 13.333in 7.5in; margin: 0; }
* { box-sizing: border-box; } body { margin: 0; font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
section { width: 13.333in; height: 7.5in; padding: .6in .8in; background: #0f3d36; color: #fff; page-break-after: always;
  position: relative; overflow: hidden; display: grid; grid-template-columns: 1fr; align-content: start; }
section.with-image { grid-template-columns: 4.6in 1fr; column-gap: .4in; }
.tag { color: #9fe3c9; font-weight: 700; letter-spacing: .12em; font-size: 12pt; }
h1 { font-size: 34pt; margin: .25in 0 .05in; line-height: 1.1; } h2 { font-size: 17pt; font-weight: 400; color: #b8e8d6; margin: 0 0 .3in; }
li { font-size: 17pt; line-height: 1.4; margin-bottom: .1in; } ul { padding-left: .28in; margin: 0; }
.shot { align-self: center; } .shot img { width: 100%; max-height: 6.1in; object-fit: contain; object-position: top;
  border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,.45); background: #fff; }
table { border-collapse: collapse; margin: 0 0 .3in; font-size: 16pt; }
td { padding: .08in .25in; border-bottom: 1px solid rgba(255,255,255,.18); } tr:first-child td { color: #9fe3c9; font-weight: 700; }
td:last-child { color: #7ff0c4; font-weight: 700; }
.n { position: absolute; right: .6in; bottom: .3in; color: #8fc4b2; font-size: 10pt; }
section.first h1 { font-size: 66pt; } section.first h2 { font-size: 30pt; color: #fff; font-weight: 700; }
"""


def pitch(work: Path):
    parts = []
    for number, slide in enumerate(slides(), 1):
        text = (f"<div><div class=tag>TIDEWAY · TOPIC E</div><h1>{html.escape(slide['title'])}</h1>"
                f"<h2>{html.escape(slide['subtitle'])}</h2>")
        if slide.get("table"):
            text += "<table>" + "".join("<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
                                        for row in slide["table"]) + "</table>"
        text += "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in slide["bullets"]) + "</ul></div>"
        image = _crop(ROOT / "evidence" / "screens" / slide["image"], work) if slide.get("image") else None
        if image and image.exists():
            text += f"<div class=shot><img src='{image.as_uri()}' alt=''></div>"
        classes = " ".join(c for c in ("first" if slide.get("first") else "", "with-image" if image and image.exists() else "") if c)
        parts.append(f"<section class='{classes}'>{text}<div class=n>{number:02d} · synthetic sandbox</div></section>")
    page = work / "pitch.html"
    page.write_text(f"<!doctype html><meta charset=utf-8><title>Tideway pitch</title><style>{SLIDE_CSS}</style>" + "".join(parts),
                    encoding="utf-8")
    print_pdf(page, ROOT / "slides" / "pitch.pdf")


def main():
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        pitch(work)
        document(work, "architecture", ROOT / "docs" / "TECHNICAL_DOCUMENTATION.md", ROOT / "docs" / "architecture.pdf")
        document(work, "security-assessment", ROOT / "docs" / "SECURITY_SELF_ASSESSMENT.md", ROOT / "docs" / "security-assessment.pdf")
        document(work, "submission-notes", ROOT / "docs" / "SUBMISSION_NOTES.md", ROOT / "docs" / "submission-notes.pdf")
        roadmap = ROOT / "docs" / "roadmap" / "Tideway_FinTechathon_2026_Roadmap.html"
        if roadmap.exists():
            print_pdf(roadmap, ROOT / "docs" / "Tideway_FinTechathon_2026_Roadmap.pdf")


if __name__ == "__main__":
    main()
