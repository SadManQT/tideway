"""Render the Tideway submission PDFs with headless Chrome (no Python packages needed).

Produces slides/pitch.pdf, docs/architecture.pdf, docs/security-assessment.pdf and
docs/Tideway_FinTechathon_2026_Roadmap.pdf (from docs/roadmap/*.html).
Requires Google Chrome; override the path with the CHROME environment variable.
"""
from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHROME = os.environ.get("CHROME") or ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                                      if sys.platform == "darwin" else "google-chrome")

DOC_CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font: 10.5pt/1.5 -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; color: #14221f; }
h1 { font-size: 22pt; color: #0f3d36; border-bottom: 3px solid #1f8a70; padding-bottom: 6px; }
h2 { font-size: 14pt; color: #0f3d36; margin-top: 20px; break-after: avoid; }
h3 { font-size: 11.5pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9pt; }
th, td { border: 1px solid #c7d6d1; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #e6f2ee; } tr { break-inside: avoid; }
code { font: 9pt ui-monospace, Menlo, monospace; background: #eef4f2; padding: 0 3px; border-radius: 3px; }
pre { background: #eef4f2; padding: 8px; font-size: 8.5pt; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; } blockquote { border-left: 4px solid #1f8a70; margin: 8px 0; padding: 2px 10px; color: #35504a; }
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
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in body) + "</table>")
        elif re.match(r"\s*(- |\d+\. )", line):
            tag = "ol" if re.match(r"\s*\d+\. ", line) else "ul"
            items = []
            while i < len(lines) and re.match(r"\s*(- |\d+\. )", lines[i]):
                items.append(re.sub(r"^\s*(- (\[[ x]\] )?|\d+\. )", "", lines[i]))
                i += 1
            i -= 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(item)}</li>" for item in items) + f"</{tag}>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
        i += 1
    return "\n".join(out)


def print_pdf(page: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={destination}", page.resolve().as_uri()],
                   check=True, capture_output=True, timeout=120)
    print(f"wrote {destination.relative_to(ROOT)}")


def document(work: Path, name: str, markdown_path: Path, destination: Path):
    page = work / f"{name}.html"
    page.write_text(f"<!doctype html><meta charset=utf-8><title>{name}</title><style>{DOC_CSS}</style>"
                    + markdown_to_html(markdown_path.read_text(encoding="utf-8")), encoding="utf-8")
    print_pdf(page, destination)


SLIDES = [
    ("Tideway", "Approval-gated cash-flow rescue for small businesses",
     ["FinTechathon 2026 · International Track · Topic E: SME Finance Copilot",
      "An agent that can read, analyse and propose, but cannot approve or execute.",
      "Synthetic sandbox: no real money, bank, lender or customer."]),
    ("The moment that matters", "Payroll is days away and cash is short",
     ["Owners need bounded choices, not another dashboard.",
      "Which bill can wait? Who can pay early? What if customers pay late?",
      "An AI that answers must never be able to move money on its own."]),
    ("A concrete case: Shapla Services (synthetic, BDT)", "Exact numbers, linked to source records",
     ["Opening cash 120,000 · payroll 80,000 · supplier bill 70,000 · confirmed receivable 20,000",
      "Scheduled minimum cash: −10,000 on 31 Oct 2026; reserve floor 20,000",
      "Reserve shortfall: 30,000. Customer habits make it worse."]),
    ("See the risk", "Customer profiles and a seeded Monte Carlo",
     ["Credibility-weighted payment profiles: own history n/(n+5), rest from the business average",
      "Three scenarios (scheduled, likely, stress) plus a 14-day look-ahead",
      "1,000 seeded runs: probability of breaching the reserve; same records, same answer"]),
    ("Plan the rescue", "An exact, risk-aware optimiser",
     ["Searches supplier deferrals, early-payment discounts and zero-cash reminders",
      "Keeps bundles that hold the reserve every day and keep payroll funded",
      "Cheapest bundle within the risk target; discounts priced as APR (2%/20 days ≈ 37%)",
      "Financing: labelled MOCK comparison only, never executable"]),
    ("Negotiate, then decide", "Simulated counterparties; human approval; signed mandate",
     ["Counterparties accept, counter or reject; a counter is a new proposal; a refusal re-plans",
      "Maker-checker with PIN step-up; two people and a typed amount above the threshold",
      "HMAC-signed mandate, modelled on AP2: scoped, expiring, tamper-evident",
      "Idempotent execution with before/after state hashes and read-back"]),
    ("Security: the model is not the weak link", "Enforcement lives outside the model",
     ["No approve or execute tool; pseudonymised names; record text never sent",
      "Hidden Unicode stripped; injection quarantined; changed-account and look-alike payee blocks",
      "Kill switch, circuit breaker, separation of duties, owner-only callback verification",
      "Hash-chained audit with witness checkpoint and tamper drill"]),
    ("Evidence", "30 of 30 sandbox cases pass",
     ["5 task cases + 25 attack cases, assuming a hijacked model and a rubber-stamp human",
      "Mapped to OWASP LLM and Agentic IDs; 15 further unit and HTTP tests",
      "Reproducible: python3 -m tideway.selftest · scripts/evaluate.py",
      "Evidence for these cases only, not proof of security"]),
    ("Honest limits and next steps", "What we have not done",
     ["Synthetic data, simulated counterparties, demo-grade PINs and keys",
      "No live-LLM measurement, no user study, no external penetration test",
      "Next: baseline comparison, consented SME interviews, a real rail adapter behind the same mandate",
      "ISO 20022 pain.001 draft shows the adapter boundary; it is never sent"]),
]

SLIDE_CSS = """
@page { size: 13.333in 7.5in; margin: 0; }
* { box-sizing: border-box; } body { margin: 0; font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; }
section { width: 13.333in; height: 7.5in; padding: 0.7in 0.9in; background: #0f3d36; color: #fff; page-break-after: always; position: relative; overflow: hidden; }
.tag { color: #9fe3c9; font-weight: 700; letter-spacing: .12em; font-size: 14pt; }
h1 { font-size: 40pt; margin: .35in 0 .05in; } h2 { font-size: 20pt; font-weight: 400; color: #b8e8d6; margin: 0 0 .35in; }
li { font-size: 21pt; line-height: 1.45; margin-bottom: .1in; } ul { padding-left: .3in; margin: 0; }
.n { position: absolute; right: .6in; bottom: .35in; color: #8fc4b2; font-size: 11pt; }
section.first h1 { font-size: 72pt; }
"""


def pitch(work: Path):
    parts = []
    for number, (title, subtitle, bullets) in enumerate(SLIDES, 1):
        parts.append(f"<section class='{'first' if number == 1 else ''}'><div class=tag>TIDEWAY · TOPIC E</div>"
                     f"<h1>{html.escape(title)}</h1><h2>{html.escape(subtitle)}</h2>"
                     "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in bullets) + "</ul>"
                     f"<div class=n>{number:02d} · synthetic sandbox · draft deck: add team details</div></section>")
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
        roadmap = ROOT / "docs" / "roadmap" / "Tideway_FinTechathon_2026_Roadmap.html"
        if roadmap.exists():
            print_pdf(roadmap, ROOT / "docs" / "Tideway_FinTechathon_2026_Roadmap.pdf")


if __name__ == "__main__":
    main()
