"""Build honest draft PDFs from the checked-in Probaho project materials.

Requires the optional reportlab package. Generated PDFs are drafts: team names,
organizer-confirmed rules, user-study findings, and live-provider measurements
must be replaced or added before a competition submission.
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]


def pitch_pdf(destination: Path):
    slides = [
        ("Probaho", "Approval-gated cash-flow recovery for small businesses\nFinTechathon 2026 · International Track · Topic E\nDRAFT — replace team details before submission"),
        ("The moment that matters", "Payroll is approaching. Cash is short.\nA small-business owner needs bounded choices, not another dashboard.\n\nProbaho turns business records into a source-linked gap, compares recovery options, and keeps the human in control."),
        ("Shapla Services · synthetic scenario", "Opening cash                         BDT 120,000\nPayroll                                   BDT 80,000\nSupplier bill                         BDT 70,000\nConfirmed receivable              BDT 20,000\nReserve floor                         BDT 20,000\n\nBase closing cash: BDT -10,000\nReserve shortfall: BDT 30,000"),
        ("From records to a decision", "1  Validate transactions, invoices, and supplier bills\n2  Project base, late-collection, and approved-recovery scenarios\n3  Compare reminder, supplier reschedule, and labelled mock financing\n4  Review payee, amount, dates, assumptions, and constraints\n5  Approve one bounded action\n6  Execute only in the synthetic sandbox and read the result back"),
        ("The boundary is the product", "The model can read and propose.\nA human approves.\nA synthetic supplier-consent event is separate.\nThe sandbox changes schedule state only.\n\nNo bank call. No lender decision. No real supplier message.\nReminders never count as collections. Mock financing never executes."),
        ("Security that a judge can inspect", "Business-scoped records and exports\nInteger-paisa deterministic calculations\nPlan + policy + snapshot hashes\nExpiry, nonce, payee, amount, date, and state checks\nSupplier-consent gate\nOne-time idempotency receipt\nPost-commit read-back\nIndependent per-business audit hash chain"),
        ("A small, explicit agent", "read_ledger\nproject_cash\ncompare_plans\ncreate_reminder_draft\n\nNo approval tool. No execute tool. No arbitrary SQL, shell, HTTP, or payments.\nRaw descriptions and counterparties are redacted before optional provider calls."),
        ("What we will measure", "Deterministic calculation correctness\nEnd-to-end task completion\nForbidden-action attempts\nRetry and replay safety\nPrompt-injection resistance\nLatency and provider cost\n3–5 consenting SME/domain reviewers\n\nThis draft reports no unmeasured user or live-model result."),
        ("Contribution and next step", "Probaho is a complete, replayable financial-agent loop:\nrecords → gap → bounded plan → human approval → sandbox receipt → evidence\n\nNext: organizer confirmation, consenting SME validation, live-provider evaluation, final English deck, and recorded demo."),
    ]
    page = landscape(A4)
    pdf = canvas.Canvas(str(destination), pagesize=page)
    width, height = page
    for index, (title, body) in enumerate(slides, 1):
        pdf.setFillColor(colors.HexColor("#153d36"))
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#c4ef9c"))
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(42, height - 42, "PROBAHO · TOPIC E")
        pdf.setFillColor(colors.white)
        pdf.setFont("Helvetica-Bold", 32 if index == 1 else 27)
        pdf.drawString(42, height - 118, title)
        text = pdf.beginText(48, height - 175)
        text.setFont("Helvetica", 17 if index == 1 else 15)
        text.setLeading(28 if index == 1 else 25)
        for line in body.splitlines():
            text.textLine(line)
        pdf.drawText(text)
        pdf.setFillColor(colors.HexColor("#a9c7b7"))
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(width - 42, 30, f"{index:02d}  ·  Draft presentation — verify all claims")
        pdf.showPage()
    pdf.save()


def document_pdf(destination: Path, title: str, subtitle: str, sections: list[tuple[str, str]]):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=22, leading=28, textColor=colors.HexColor("#153d36"), spaceAfter=10))
    styles.add(ParagraphStyle(name="DocSub", parent=styles["Normal"], fontSize=10, leading=15, textColor=colors.HexColor("#657178"), spaceAfter=18))
    styles.add(ParagraphStyle(name="DocHead", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#235447"), spaceBefore=14, spaceAfter=6))
    styles.add(ParagraphStyle(name="DocBody", parent=styles["BodyText"], fontSize=9.5, leading=14, spaceAfter=8))
    story = [Paragraph(title, styles["DocTitle"]), Paragraph(subtitle, styles["DocSub"])]
    for heading, body in sections:
        story.extend([Paragraph(heading, styles["DocHead"]), Paragraph(body.replace("\n", "<br/>"), styles["DocBody"])])
    doc = SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=48, leftMargin=48, topMargin=48, bottomMargin=44)
    doc.build(story)


def main():
    (ROOT / "slides").mkdir(exist_ok=True)
    pitch_pdf(ROOT / "slides" / "pitch.pdf")
    document_pdf(ROOT / "docs" / "architecture.pdf", "Probaho — Architecture", "Draft generated from the checked-in Topic E implementation; review with the team before submission.", [
        ("Scope", "A local-first, synthetic SME cash-flow recovery workflow: scoped records, deterministic projections, bounded plan comparison, approval, synthetic supplier consent, sandbox execution, read-back, and evidence."),
        ("Runtime path", "Browser UI → loopback HTTP API → validated domain functions → scoped SQLite → deterministic projections and plan comparisons → snapshot-bound approval → supplier-consent gate → idempotent sandbox receipt."),
        ("Projection", "Integer BDT paisa; base, late-collection, and approved-recovery scenarios; pre-opening history excluded; paid/collected invoices excluded; daily reserve and payroll checks; source references attached to events."),
        ("Agent boundary", "Scoped requests expose read_ledger, project_cash, compare_plans, and create_reminder_draft only. The model cannot approve, execute, send money, call arbitrary APIs, or access raw record descriptions."),
        ("Evidence", "Plan hash, snapshot hash, policy version, approval fields, consent fields, action fingerprints, before/after state, projection before/after, read-back, idempotency key, and per-business SHA-256 audit chain."),
        ("Limitations", "No real bank, lender, supplier, multi-user authentication, encrypted storage, or production compliance. The synthetic sandbox demonstrates control flow, not deployment readiness."),
    ])
    document_pdf(ROOT / "docs" / "security-assessment.pdf", "Probaho — Security self-assessment", "Draft PDF generated from docs/SECURITY_SELF_ASSESSMENT.md; this is not a certification.", [
        ("Permission tiers", "agent_read; agent_propose; human_approval; sandbox_execute; user_write; denied. Approval and execution are absent from the model tool surface."),
        ("Core controls", "Business scoping, integer-paisa arithmetic, whole-file import validation, snapshot hashes, policy limits, expiry and nonce, payee/date/amount rechecks, explicit synthetic supplier consent, idempotent execution, and post-commit read-back."),
        ("Abuse cases", "Prompt injection, cross-business IDs, direct execution, missing/rejected consent, changed payee, changed amount/date, expired approval, replay, stale balance, payroll deferral, policy overflow, mixed currency, malformed CSV, formula export, and cross-site writes."),
        ("Residual risk", "The local database is unencrypted and rewritable, the operator is not multi-user authenticated, the hash chain is not externally notarized, and model output remains probabilistic. No real-money capability is connected."),
        ("Release gate", "Disable execution until unauthorized mutation is zero, deterministic calculations reconcile, reminders remain zero-cash, mock financing is non-executable, changed approvals fail, read-back exists, and the evidence chain verifies."),
    ])
    print("Built slides/pitch.pdf, docs/architecture.pdf, and docs/security-assessment.pdf")


if __name__ == "__main__":
    main()
