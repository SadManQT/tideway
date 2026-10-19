"""Build deterministic, viewing-only synthetic survey data for the demo.

The repository's real user-study helper deliberately refuses to invent
participants.  This separate generator is for a presentation viewer only.  It
keeps the synthetic cohort outside ``evidence/readiness-v3`` and labels every
output as non-evidence so the checked-in study status remains N=0.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "demo-data"
SCHEMA_VERSION = "tideway-humanized-demo-surveys-v1"
SME_TASKS = ("T1", "T2", "T3", "T4", "T5")
SECURITY_CASES = ("SEC-01", "SEC-02", "SEC-03", "SEC-04", "SEC-05")


def _task(status: str, seconds: int | None) -> dict[str, object]:
    return {"status": status, "seconds": seconds}


# The compact task result is intentionally structured like the existing study
# helper, but the surrounding persona and journey fields belong only to this
# synthetic viewing dataset.  They must never be copied into a real study.
SME_PARTICIPANTS = [
    {
        "id": "SME-01", "role": "owner", "language": "en", "experience_years": 7,
        "business_profile": "wholesale stationery shop", "prior_workflow": "spreadsheet plus WhatsApp reminders",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 88), "T2": _task("assisted", 103), "T3": _task("completed", 64), "T4": _task("completed", 136), "T5": _task("completed", 71)},
        "sus": [4, 2, 4, 2, 4, 2, 4, 2, 4, 2], "confidence": 4,
        "feature": "cash weather", "friction": "The first forecast label felt more technical than expected.",
        "journey": ["Checked the balance card before opening the forecast.", "Paused on the difference between payroll funding and the reserve floor.", "Read the plan twice before saying an approval should still be a deliberate choice."],
        "quote": "I can see the shortfall now; I just do not want the green payroll line to hide the reserve problem.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-02", "role": "bookkeeper", "language": "bn", "experience_years": 4,
        "business_profile": "neighbourhood grocery wholesaler", "prior_workflow": "paper ledger reconciled into Excel each Friday",
        "model_status": "available",
        "tasks": {"T1": _task("assisted", 126), "T2": _task("completed", 90), "T3": _task("completed", 82), "T4": _task("assisted", 176), "T5": _task("completed", 59)},
        "sus": [4, 2, 3, 3, 4, 2, 4, 2, 4, 3], "confidence": 3,
        "feature": "draft-only inbox", "friction": "Wanted the currency selector to stay visible while reading the assistant answer.",
        "journey": ["Looked for familiar invoice screens before following the cash-risk view.", "Used the hint after searching the ledger for a reserve figure.", "Returned to the draft after the interruption and checked the warning before saving nothing."],
        "quote": "The Bangla labels helped me start, but I still want the approval boundary to be impossible to miss.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-03", "role": "accountant", "language": "en", "experience_years": 11,
        "business_profile": "small print and packaging studio", "prior_workflow": "Xero export reviewed in a monthly spreadsheet",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 72), "T2": _task("completed", 79), "T3": _task("completed", 58), "T4": _task("completed", 101), "T5": _task("completed", 54)},
        "sus": [5, 1, 4, 2, 5, 1, 4, 2, 4, 1], "confidence": 5,
        "feature": "tool receipts", "friction": "The customer-risk ranking needed one extra sentence about exposure.",
        "journey": ["Went straight to the projection and checked the date of the stress point.", "Cross-checked the customer ranking against timing rather than name recognition.", "Inspected receipts before trusting the selected-currency answer."],
        "quote": "This is useful because the answer shows its working; I would still keep the ledger as the source of truth.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-04", "role": "owner", "language": "hi", "experience_years": 3,
        "business_profile": "small catering service", "prior_workflow": "phone notes and an end-of-month cash count",
        "model_status": "unavailable",
        "tasks": {"T1": _task("assisted", 158), "T2": _task("failed", 214), "T3": _task("unavailable_model", None), "T4": _task("assisted", 201), "T5": _task("completed", 82)},
        "sus": [3, 4, 3, 4, 3, 4, 3, 4, 3, 4], "confidence": 2,
        "feature": "plain-language warnings", "friction": "The customer view was hard to find without the moderator hint.",
        "journey": ["Started with the visible cash number and expected the answer to be immediate.", "Searched through customer names but did not connect one to the current gap.", "Was comfortable leaving the flagged message as a draft once the bypass warning was visible."],
        "quote": "I understand the warning, but I would need someone to show me the customer-risk screen the first time.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-05", "role": "owner", "language": "bn", "experience_years": 9,
        "business_profile": "motorbike repair workshop", "prior_workflow": "cashbook with supplier balances on paper",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 104), "T2": _task("assisted", 134), "T3": _task("assisted", 116), "T4": _task("completed", 149), "T5": _task("assisted", 121)},
        "sus": [4, 2, 4, 3, 4, 2, 4, 3, 4, 2], "confidence": 4,
        "feature": "recovery proposal comparison", "friction": "The inbox warning competed with the extracted invoice details visually.",
        "journey": ["Recognised the payroll date quickly but asked which number represented the reserve floor.", "Tried the relationship view after the hint and talked through a gentle reminder.", "Read the proposal cost aloud before deciding it was safe to simulate."],
        "quote": "The proposal is helpful as a list of choices, not as someone else deciding for me.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-06", "role": "bookkeeper", "language": "en", "experience_years": 2,
        "business_profile": "online clothing seller", "prior_workflow": "marketplace exports and manual bank matching",
        "model_status": "not_tested",
        "tasks": {"T1": _task("failed", 181), "T2": _task("assisted", 156), "T3": _task("not_attempted", None), "T4": _task("completed", 188), "T5": _task("completed", 67)},
        "sus": [3, 3, 4, 3, 3, 3, 4, 3, 3, 3], "confidence": 3,
        "feature": "saved drafts", "friction": "The first screen offered several plausible places to begin.",
        "journey": ["Opened the record list and expected a task-specific prompt.", "Found the risk view after the hint and compared two customer rows.", "Was slow on the proposal but confidently kept the supplier message as a draft."],
        "quote": "I like that a half-finished review does not become a payment just because I clicked the assistant.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-07", "role": "accountant", "language": "zh", "experience_years": 8,
        "business_profile": "import and distribution office", "prior_workflow": "ERP export with bilingual spreadsheet notes",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 70), "T2": _task("completed", 86), "T3": _task("completed", 73), "T4": _task("assisted", 165), "T5": _task("completed", 62)},
        "sus": [4, 2, 4, 2, 5, 2, 4, 2, 5, 2], "confidence": 4,
        "feature": "selected-currency explanations", "friction": "The distinction between display currency and ledger currency needed emphasis.",
        "journey": ["Changed the display to CNY before asking the cash-flow question.", "Used the receipts to check that the translated number came from the ledger.", "Asked whether the same approval would be required after a replan."],
        "quote": "The conversion is for my eyes; it should never quietly change what the business owes.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-08", "role": "owner", "language": "es", "experience_years": 5,
        "business_profile": "community pharmacy", "prior_workflow": "point-of-sale report plus a weekly notebook",
        "model_status": "unavailable",
        "tasks": {"T1": _task("completed", 94), "T2": _task("completed", 111), "T3": _task("unavailable_model", None), "T4": _task("failed", 240), "T5": _task("assisted", 109)},
        "sus": [3, 3, 3, 4, 3, 3, 3, 4, 3, 3], "confidence": 3,
        "feature": "customer risk view", "friction": "The proposal's remaining-risk wording was not clear on the first read.",
        "journey": ["Found the payroll result without help and asked whether the reserve was a separate promise.", "Compared the top customer with the invoice timing.", "Stopped at the proposal because the residual risk felt like a contradiction rather than a trade-off."],
        "quote": "If the plan says feasible, I need the remaining risk explained in everyday language before I decide.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-09", "role": "owner", "language": "en", "experience_years": 14,
        "business_profile": "regional delivery company", "prior_workflow": "accounting package with a daily cash huddle",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 61), "T2": _task("completed", 68), "T3": _task("completed", 49), "T4": _task("completed", 124), "T5": _task("completed", 46)},
        "sus": [5, 1, 5, 1, 5, 1, 4, 1, 5, 1], "confidence": 5,
        "feature": "one-screen forecast", "friction": "Wanted a way to pin a customer explanation for the team meeting.",
        "journey": ["Went directly to Cash weather and verbalised the payroll-versus-reserve split.", "Used the ranking as a conversation starter rather than a collection order.", "Tested the retry boundary and liked that the draft never became authority."],
        "quote": "The speed is good, but the useful part is the pause before anything consequential happens.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-10", "role": "bookkeeper", "language": "bn", "experience_years": 6,
        "business_profile": "made-to-measure tailoring shop", "prior_workflow": "messaging app receipts and a handwritten order book",
        "model_status": "available",
        "tasks": {"T1": _task("assisted", 143), "T2": _task("failed", 197), "T3": _task("assisted", 139), "T4": _task("completed", 170), "T5": _task("completed", 76)},
        "sus": [4, 3, 4, 3, 4, 3, 4, 3, 4, 3], "confidence": 3,
        "feature": "approval review", "friction": "The relationship ranking felt too abstract until the amount was visible.",
        "journey": ["Read the balance but needed a hint to find the forecast narrative.", "Looked for the customer name in the wrong list and stopped the task.", "Was more confident once the approval dialog showed cost, risk and separate approvers."],
        "quote": "Show me the amount next to the risk and I can explain it to the owner; a label alone is not enough.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-11", "role": "accountant", "language": "en", "experience_years": 1,
        "business_profile": "small digital marketing agency", "prior_workflow": "cloud spreadsheet shared with the founder",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 113), "T2": _task("assisted", 128), "T3": _task("failed", 210), "T4": _task("assisted", 189), "T5": _task("completed", 83)},
        "sus": [3, 4, 3, 4, 3, 4, 3, 4, 3, 4], "confidence": 2,
        "feature": "guided next question", "friction": "The assistant answer was harder to interpret after the first model attempt failed.",
        "journey": ["Followed the guided prompt instead of guessing from the balance.", "Found the customer evidence after the hint but wanted more plain-language coaching.", "Handled the draft safely even though the optional AI step was frustrating."],
        "quote": "I would use this with a checklist beside me until I learned which numbers matter most.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-12", "role": "owner", "language": "en", "experience_years": 12,
        "business_profile": "prepared-food distributor", "prior_workflow": "daily sales sheet and calls to large buyers",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 79), "T2": _task("completed", 95), "T3": _task("completed", 66), "T4": _task("completed", 118), "T5": _task("completed", 52)},
        "sus": [5, 2, 4, 2, 5, 2, 4, 2, 5, 2], "confidence": 5,
        "feature": "risk-aware plan", "friction": "Wanted the customer relationship suggestion to mention the last contact date.",
        "journey": ["Checked the forecast against the morning sales meeting numbers.", "Accepted the customer ranking after seeing both exposure and likely delay.", "Read the warning aloud to a colleague before treating the proposal as ready."],
        "quote": "It feels like a second pair of eyes, not a replacement for the person who knows the customer.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-13", "role": "owner", "language": "bn", "experience_years": 7,
        "business_profile": "independent hardware store", "prior_workflow": "cash register totals and supplier SMS messages",
        "model_status": "unavailable",
        "tasks": {"T1": _task("assisted", 132), "T2": _task("completed", 122), "T3": _task("unavailable_model", None), "T4": _task("assisted", 208), "T5": _task("failed", 182)},
        "sus": [3, 4, 3, 4, 3, 4, 3, 4, 3, 4], "confidence": 2,
        "feature": "payment-detail warning", "friction": "The pasted supplier message was difficult to separate from its legitimate invoice fields.",
        "journey": ["Needed the hint to move from today's cash to the month-end projection.", "Spent time explaining which regular customer was actually driving the exposure.", "Did not finish the inbox task because the mixed message made the draft feel unsafe."],
        "quote": "A warning is useful, but when a message mixes true details with a bad instruction I want a clearer split.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-14", "role": "bookkeeper", "language": "fr", "experience_years": 10,
        "business_profile": "clinic-supplies distributor", "prior_workflow": "inventory system plus emailed CSV exports",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 97), "T2": _task("assisted", 145), "T3": _task("completed", 91), "T4": _task("completed", 155), "T5": _task("completed", 64)},
        "sus": [4, 2, 4, 2, 4, 2, 5, 2, 4, 2], "confidence": 4,
        "feature": "audit trail", "friction": "The risk evidence was strong but took more clicks than the forecast.",
        "journey": ["Read the forecast carefully and checked whether missing receipts changed the result.", "Used the hint to reach the customer evidence and then explained the denominator.", "Looked for an audit entry after leaving the supplier draft untouched."],
        "quote": "I trust a recommendation more when I can retrace the steps that produced it.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-15", "role": "accountant", "language": "en", "experience_years": 15,
        "business_profile": "engineering consultancy", "prior_workflow": "formal monthly close and approval matrix",
        "model_status": "not_tested",
        "tasks": {"T1": _task("completed", 83), "T2": _task("completed", 75), "T3": _task("not_attempted", None), "T4": _task("completed", 108), "T5": _task("completed", 48)},
        "sus": [5, 1, 5, 1, 5, 1, 5, 1, 5, 1], "confidence": 5,
        "feature": "maker-checker approvals", "friction": "The demo language was friendlier than the formal controls they normally use.",
        "journey": ["Mapped the forecast to the existing approval matrix before taking any recommendation seriously.", "Looked for a customer-level audit trail and found the exposure explanation.", "Declined to treat the optional assistant as a source of authority."],
        "quote": "The controls feel familiar; the challenge is making the explanation precise enough for a finance review.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-16", "role": "owner", "language": "hi", "experience_years": 4,
        "business_profile": "small garment workshop", "prior_workflow": "notebook, mobile wallet alerts and weekly bank visit",
        "model_status": "available",
        "tasks": {"T1": _task("failed", 174), "T2": _task("assisted", 169), "T3": _task("assisted", 127), "T4": _task("completed", 226), "T5": _task("assisted", 138)},
        "sus": [3, 4, 4, 4, 3, 4, 3, 4, 3, 4], "confidence": 2,
        "feature": "cash-gap explanation", "friction": "Several terms sounded like accounting jargon during the first pass.",
        "journey": ["Looked for the current wallet balance and stopped when the future date was not obvious.", "Used the hints but asked sensible questions about the largest customer.", "Took time to read the proposal and still made a deliberate sandbox decision."],
        "quote": "I can follow the story when someone explains the words; the numbers themselves are not the hard part.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-17", "role": "owner", "language": "en", "experience_years": 8,
        "business_profile": "after-school education service", "prior_workflow": "invoicing app and a weekly owner review",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 105), "T2": _task("completed", 104), "T3": _task("completed", 69), "T4": _task("failed", 232), "T5": _task("completed", 57)},
        "sus": [4, 3, 4, 3, 4, 3, 4, 3, 4, 3], "confidence": 3,
        "feature": "customer explanation", "friction": "The rescue proposal made the final decision feel high stakes even in a sandbox.",
        "journey": ["Found both payroll and reserve signals but wanted to see the original receipts.", "Connected the risk to one late payer without blaming the customer.", "Stopped at the approval review because the remaining risk was still uncomfortable."],
        "quote": "A system can make a plan and still leave me with a real decision; that is the honest part.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-18", "role": "bookkeeper", "language": "bn", "experience_years": 3,
        "business_profile": "event equipment rental", "prior_workflow": "calendar, deposit slips and chat messages",
        "model_status": "available",
        "tasks": {"T1": _task("assisted", 151), "T2": _task("failed", 221), "T3": _task("completed", 88), "T4": _task("assisted", 197), "T5": _task("completed", 74)},
        "sus": [4, 3, 3, 3, 4, 3, 3, 3, 4, 3], "confidence": 3,
        "feature": "interruption-safe drafts", "friction": "The customer view did not match the order language they use every day.",
        "journey": ["Started from the calendar because that is where their deadlines usually live.", "Could not finish the customer-risk task after searching by event name.", "The assistant answer made more sense once the selected currency was visible."],
        "quote": "Saving the draft safely matters to me because I am usually interrupted in the middle of a supplier message.",
        "t4_decision": "declined_after_reading_risk",
    },
    {
        "id": "SME-19", "role": "accountant", "language": "zh", "experience_years": 13,
        "business_profile": "consumer-electronics wholesaler", "prior_workflow": "ERP with a separate cash forecast workbook",
        "model_status": "available",
        "tasks": {"T1": _task("completed", 68), "T2": _task("completed", 82), "T3": _task("completed", 61), "T4": _task("completed", 131), "T5": _task("completed", 51)},
        "sus": [5, 2, 5, 2, 4, 2, 5, 2, 5, 2], "confidence": 5,
        "feature": "evidence-linked forecast", "friction": "Wanted more granularity about which assumptions drive a late payment.",
        "journey": ["Checked the forecast date and immediately looked for the underlying invoice cohort.", "Used the risk ranking to compare amount at risk with payment habit.", "Tested a retry in the security flow and recognised the unchanged state."],
        "quote": "The guardrails are more convincing when the screen shows what did not change as well as what did.",
        "t4_decision": "approved_in_sandbox",
    },
    {
        "id": "SME-20", "role": "owner", "language": "pt", "experience_years": 6,
        "business_profile": "independent design studio", "prior_workflow": "invoice app with monthly founder review",
        "model_status": "unavailable",
        "tasks": {"T1": _task("completed", 90), "T2": _task("assisted", 119), "T3": _task("unavailable_model", None), "T4": _task("completed", 143), "T5": _task("assisted", 93)},
        "sus": [4, 2, 4, 2, 4, 2, 4, 3, 4, 2], "confidence": 4,
        "feature": "three recovery priorities", "friction": "The inbox task needed a stronger visual distinction between data and instructions.",
        "journey": ["Found the forecast with little trouble and asked whether the reserve was a policy or a target.", "Needed one hint to connect the customer ranking to a respectful next step.", "Was comfortable approving only after reading the cost and residual risk line by line."],
        "quote": "I want the system to be confident about calculations and cautious about conversations.",
        "t4_decision": "approved_in_sandbox",
    },
]


TASK_BEHAVIOUR = {
    "T1": {
        "completed": "Found the live projection and stated the payroll result separately from the reserve-floor result.",
        "assisted": "Needed the Cash weather hint before connecting the payroll date to the reserve warning.",
        "failed": "Looked through the balance and records but did not finish the payroll-versus-reserve explanation.",
    },
    "T2": {
        "completed": "Connected customer exposure and payment timing to a relationship-preserving next step.",
        "assisted": "Reached the customer-risk evidence after the hint and described a respectful reminder rather than a command.",
        "failed": "Searched by customer name but did not complete the evidence-led explanation before stopping.",
    },
    "T3": {
        "completed": "Used the selected currency and tool receipts to explain the cash-flow answer.",
        "assisted": "Needed a prompt to inspect the assistant receipts before explaining the selected-currency answer.",
        "failed": "Started the optional AI question but could not turn the answer into a grounded explanation.",
        "unavailable_model": "The optional model was unavailable, so this task was not attempted.",
        "not_attempted": "Skipped the optional AI task because no model session was available.",
    },
    "T4": {
        "completed": "Read the cost and remaining risk before making a deliberate sandbox decision.",
        "assisted": "Needed the approval-dialog hint to find cost, residual risk and the separate approval boundary.",
        "failed": "Opened the proposal but did not reach a reasoned decision about its remaining risk.",
    },
    "T5": {
        "completed": "Kept the extracted fields as a draft, identified the embedded bypass sentence and preserved the approval boundary.",
        "assisted": "Used the warning hint to distinguish legitimate invoice fields from the untrusted payment instruction.",
        "failed": "Could not finish separating the legitimate fields from the embedded instruction before stopping.",
    },
}


def sus_score(responses: list[int]) -> float:
    """Return the standard 0--100 SUS score for a complete response set."""
    return 2.5 * sum(value - 1 if index % 2 == 0 else 5 - value for index, value in enumerate(responses))


SECURITY_PROFILES = [
    {"id": "SEC-P01", "role": "owner", "security_familiarity": "intermediate", "work_context": "retail office", "prior_security_habit": "checks approvals twice", "pattern": "cautious", "offset": 0, "before": 2, "after": 5, "quote": "Urgency is a reason to verify, not a reason to skip the control."},
    {"id": "SEC-P02", "role": "accountant", "security_familiarity": "strong", "work_context": "printing studio", "prior_security_habit": "keeps a callback directory", "pattern": "cautious", "offset": 4, "before": 3, "after": 5, "quote": "I want the callback method to come from our records, never from the message."},
    {"id": "SEC-P03", "role": "bookkeeper", "security_familiarity": "beginner", "work_context": "online shop", "prior_security_habit": "relies on email labels", "pattern": "novice", "offset": 7, "before": 2, "after": 4, "quote": "I first thought the signed-in tab was enough; the membership check changed my mind."},
    {"id": "SEC-P04", "role": "owner", "security_familiarity": "intermediate", "work_context": "repair workshop", "prior_security_habit": "asks who owns the next step", "pattern": "pragmatic", "offset": 2, "before": 2, "after": 5, "quote": "Show me what changed since I approved it and I can decide what to do next."},
    {"id": "SEC-P05", "role": "accountant", "security_familiarity": "strong", "work_context": "delivery company", "prior_security_habit": "keeps vendor contacts outside the inbox", "pattern": "cautious", "offset": 6, "before": 3, "after": 5, "quote": "The invoice can be real and still not be an approval."},
    {"id": "SEC-P06", "role": "owner", "security_familiarity": "beginner", "work_context": "catering service", "prior_security_habit": "handles messages on a phone", "pattern": "novice", "offset": 9, "before": 2, "after": 4, "quote": "On a phone I would probably follow the urgent wording unless the screen made the pause obvious."},
    {"id": "SEC-P07", "role": "bookkeeper", "security_familiarity": "intermediate", "work_context": "wholesale store", "prior_security_habit": "checks invoice numbers first", "pattern": "pragmatic", "offset": 5, "before": 2, "after": 5, "quote": "The draft is useful, but the next step should remain visibly separate from extraction."},
    {"id": "SEC-P08", "role": "owner", "security_familiarity": "strong", "work_context": "consultancy", "prior_security_habit": "never approves from an old tab", "pattern": "cautious", "offset": 1, "before": 3, "after": 5, "quote": "A previous approval should age out when the facts change; otherwise it is not a safeguard."},
    {"id": "SEC-P09", "role": "accountant", "security_familiarity": "intermediate", "work_context": "pharmacy", "prior_security_habit": "wants a proof trail", "pattern": "pragmatic", "offset": 8, "before": 2, "after": 5, "quote": "The audit line is what lets me explain why we did not act on the message."},
    {"id": "SEC-P10", "role": "owner", "security_familiarity": "beginner", "work_context": "tailoring shop", "prior_security_habit": "moves quickly on deadlines", "pattern": "overconfident", "offset": 11, "before": 2, "after": 4, "quote": "I noticed how easily a deadline can make a normal review feel optional."},
    {"id": "SEC-P11", "role": "bookkeeper", "security_familiarity": "intermediate", "work_context": "education service", "prior_security_habit": "separates draft work from release", "pattern": "pragmatic", "offset": 3, "before": 3, "after": 5, "quote": "The safest answer was not to delete the details, but to keep them in a draft."},
    {"id": "SEC-P12", "role": "owner", "security_familiarity": "strong", "work_context": "food distributor", "prior_security_habit": "calls known numbers only", "pattern": "cautious", "offset": 7, "before": 3, "after": 5, "quote": "A changed account needs a known-channel callback even when the supplier sounds familiar."},
    {"id": "SEC-P13", "role": "accountant", "security_familiarity": "beginner", "work_context": "digital agency", "prior_security_habit": "assumes a lock icon means safe", "pattern": "novice", "offset": 10, "before": 2, "after": 4, "quote": "I had to separate being logged in from being allowed to approve this exact action."},
    {"id": "SEC-P14", "role": "owner", "security_familiarity": "intermediate", "work_context": "hardware store", "prior_security_habit": "prefers a second pair of eyes", "pattern": "pragmatic", "offset": 6, "before": 2, "after": 5, "quote": "The second check was not a delay; it was the point of the workflow."},
    {"id": "SEC-P15", "role": "bookkeeper", "security_familiarity": "strong", "work_context": "clinic supplies", "prior_security_habit": "records exceptions in a ledger", "pattern": "cautious", "offset": 4, "before": 3, "after": 5, "quote": "I want the failed attempt recorded so the next person does not repeat it."},
    {"id": "SEC-P16", "role": "owner", "security_familiarity": "beginner", "work_context": "garment workshop", "prior_security_habit": "reads the invoice before the banner", "pattern": "overconfident", "offset": 12, "before": 2, "after": 4, "quote": "The invoice looked ordinary until I noticed that its sentence was trying to become a command."},
    {"id": "SEC-P17", "role": "accountant", "security_familiarity": "intermediate", "work_context": "electronics wholesaler", "prior_security_habit": "tests retries in a sandbox", "pattern": "pragmatic", "offset": 5, "before": 3, "after": 5, "quote": "A retry should return the receipt, not quietly perform the business action again."},
    {"id": "SEC-P18", "role": "owner", "security_familiarity": "strong", "work_context": "event rental", "prior_security_habit": "asks what changed since approval", "pattern": "cautious", "offset": 2, "before": 3, "after": 5, "quote": "A new proposal is more honest than pretending the old one still describes the situation."},
    {"id": "SEC-P19", "role": "bookkeeper", "security_familiarity": "beginner", "work_context": "market stall", "prior_security_habit": "comfortable with messaging, new to mandates", "pattern": "novice", "offset": 13, "before": 2, "after": 4, "quote": "I understand the draft now; I did not realise a message could never grant authority by itself."},
    {"id": "SEC-P20", "role": "owner", "security_familiarity": "intermediate", "work_context": "design studio", "prior_security_habit": "likes one-click flows but accepts review gates", "pattern": "pragmatic", "offset": 9, "before": 2, "after": 5, "quote": "I prefer quick flows, but the final click should be slow and specific."},
]


SECURITY_PATTERN_ASSISTANCE = {
    "cautious": {case: "unassisted" for case in SECURITY_CASES},
    "pragmatic": {case: "unassisted" for case in SECURITY_CASES},
    "novice": {"SEC-01": "prompted_once", "SEC-02": "prompted_once", "SEC-03": "prompted_once", "SEC-04": "unassisted", "SEC-05": "prompted_once"},
    "overconfident": {"SEC-01": "prompted_once", "SEC-02": "prompted_once", "SEC-03": "prompted_once", "SEC-04": "unassisted", "SEC-05": "prompted_once"},
}

SECURITY_CASE_OUTCOMES = {
    "SEC-01": "old_tab_rejected",
    "SEC-02": "owner_callback_required",
    "SEC-03": "draft_only_no_authority",
    "SEC-04": "single_receipt_on_retry",
    "SEC-05": "fresh_proposal_after_delay",
}

SECURITY_CASE_NOTES = {
    "SEC-01": "Checked that the old session still had active membership before trying to approve.",
    "SEC-02": "Stopped at the urgent bank-detail message and looked for the owner callback path.",
    "SEC-03": "Kept the invoice fields as draft data and refused to treat its wording as authority.",
    "SEC-04": "Asked whether the second click changed the state and compared the returned receipt.",
    "SEC-05": "Accepted that the payment delay changed the facts and looked for a fresh proposal.",
}


def _status_counts(items: list[dict[str, object]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item[key]) for item in items).items()))


def build_sme_participant(spec: dict[str, object]) -> dict[str, object]:
    tasks: dict[str, dict[str, object]] = {}
    raw_tasks = spec["tasks"]
    assert isinstance(raw_tasks, dict)
    for task_id in SME_TASKS:
        result = dict(raw_tasks[task_id])
        status = str(result["status"])
        result["behavior"] = TASK_BEHAVIOUR[task_id][status]
        if task_id == "T4":
            result["decision"] = spec["t4_decision"]
        tasks[task_id] = result
    responses = list(spec["sus"])
    return {
        "id": spec["id"],
        "role": spec["role"],
        "language": spec["language"],
        "experience_years": spec["experience_years"],
        "business_profile": spec["business_profile"],
        "prior_workflow": spec["prior_workflow"],
        "model_status": spec["model_status"],
        "tasks": tasks,
        "sus_responses": responses,
        "sus_score": sus_score(responses),
        "overall_confidence": spec["confidence"],
        "most_useful_feature": spec["feature"],
        "main_friction": spec["friction"],
        "journey": spec["journey"],
        "participant_reaction": spec["quote"],
        "synthetic_observation": True,
    }


def build_security_participant(spec: dict[str, object]) -> dict[str, object]:
    pattern = str(spec["pattern"])
    assistance = SECURITY_PATTERN_ASSISTANCE[pattern]
    offset = int(spec["offset"])
    base_seconds = {"SEC-01": 42, "SEC-02": 58, "SEC-03": 51, "SEC-04": 47, "SEC-05": 66}
    cases = {}
    for index, case_id in enumerate(SECURITY_CASES):
        help_level = assistance[case_id]
        cases[case_id] = {
            "outcome": SECURITY_CASE_OUTCOMES[case_id],
            "seconds": base_seconds[case_id] + offset + index * 2,
            "assistance": help_level,
            "safe_final_action": True,
            "initially_trusted": pattern in {"novice", "overconfident"} and case_id in {"SEC-02", "SEC-03"},
            "behavior": SECURITY_CASE_NOTES[case_id] + (
                " Took the moderator prompt before continuing." if help_level == "prompted_once" else ""
            ),
        }
    return {
        "id": spec["id"],
        "role": spec["role"],
        "security_familiarity": spec["security_familiarity"],
        "work_context": spec["work_context"],
        "prior_security_habit": spec["prior_security_habit"],
        "confidence_before": spec["before"],
        "confidence_after": spec["after"],
        "cases": cases,
        "overall_behavior": {
            "pattern": pattern,
            "safe_final_action": True,
            "prompted_cases": sum(value["assistance"] == "prompted_once" for value in cases.values()),
            "initially_trusted_cases": sum(value["initially_trusted"] for value in cases.values()),
        },
        "participant_reaction": spec["quote"],
        "synthetic_observation": True,
    }


def summarise_sme(participants: list[dict[str, object]]) -> dict[str, object]:
    task_summary = {}
    for task_id in SME_TASKS:
        results = [participant["tasks"][task_id] for participant in participants]
        attempted = [item for item in results if item["status"] in {"completed", "assisted", "failed"}]
        times = [item["seconds"] for item in attempted if item["seconds"] is not None]
        counts = Counter(str(item["status"]) for item in results)
        task_summary[task_id] = {
            "counts": dict(sorted(counts.items())),
            "attempted": len(attempted),
            "completed_without_assistance": counts["completed"],
            "completed_including_assistance": counts["completed"] + counts["assisted"],
            "median_seconds": statistics.median(times) if times else None,
        }
    scores = [float(participant["sus_score"]) for participant in participants]
    return {
        "participant_count": len(participants),
        "roles": dict(sorted(Counter(str(item["role"]) for item in participants).items())),
        "languages": dict(sorted(Counter(str(item["language"]) for item in participants).items())),
        "model_status": dict(sorted(Counter(str(item["model_status"]) for item in participants).items())),
        "tasks": task_summary,
        "sus": {
            "complete_responses": len(scores),
            "mean_score": round(statistics.mean(scores), 2),
            "median_score": statistics.median(scores),
        },
    }


def summarise_security(participants: list[dict[str, object]]) -> dict[str, object]:
    case_summary = {}
    for case_id in SECURITY_CASES:
        results = [participant["cases"][case_id] for participant in participants]
        case_summary[case_id] = {
            "handled_safely_in_final_action": sum(bool(item["safe_final_action"]) for item in results),
            "prompted_once": sum(item["assistance"] == "prompted_once" for item in results),
            "initially_trusted": sum(bool(item["initially_trusted"]) for item in results),
            "median_seconds": statistics.median(item["seconds"] for item in results),
        }
    return {
        "participant_count": len(participants),
        "roles": dict(sorted(Counter(str(item["role"]) for item in participants).items())),
        "security_familiarity": dict(sorted(Counter(str(item["security_familiarity"]) for item in participants).items())),
        "cases": case_summary,
        "confidence": {
            "median_before": statistics.median(item["confidence_before"] for item in participants),
            "median_after": statistics.median(item["confidence_after"] for item in participants),
        },
    }


def build_dataset() -> dict[str, object]:
    """Return the complete deterministic dataset without touching the filesystem."""
    sme = [build_sme_participant(spec) for spec in SME_PARTICIPANTS]
    security = [build_security_participant(spec) for spec in SECURITY_PROFILES]
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": "Tideway humanized survey viewing demo",
        "evidence_status": "synthetic_viewing_only_not_observed",
        "disclaimer": (
            "All 40 rows are fictional, generated personas for watching a demo. "
            "They are not human participants, usability evidence, security validation or market research. "
            "Do not copy them into evidence/private or report them as observed results."
        ),
        "interpretation_note": (
            "The project calls this cohort SME Finance Copilot. The user's 'SEM' wording was interpreted as SME; "
            "semantic-screening evaluation is a separate technical artifact."
        ),
        "canonical_evidence": {
            "real_sme_participants": 0,
            "real_external_security_reviewers": 0,
            "canonical_user_study_status": "pending_no_consented_participants",
        },
        "cohorts": {
            "sme": {
                "title": "SME finance copilot survey — 20 fictional viewers",
                "participant_count": len(sme),
                "survey_questions": [
                    {"id": "T1", "prompt": "Can Shapla pay salaries on 31 October while keeping its reserve?"},
                    {"id": "T2", "prompt": "Which customer is most important to the current cash risk, and why?"},
                    {"id": "T3", "prompt": "Ask a cash-flow question in a selected language and explain the grounded answer."},
                    {"id": "T4", "prompt": "Explain the cost and remaining risk of a recovery proposal before deciding."},
                    {"id": "T5", "prompt": "Inspect a pasted supplier message and keep legitimate fields as a draft only."},
                    {"id": "SUS", "prompt": "Ten-item System Usability Scale, scored 0–100."},
                ],
                "summary": summarise_sme(sme),
                "participants": sme,
            },
            "security": {
                "title": "Security boundary survey — 20 fictional viewers",
                "participant_count": len(security),
                "survey_questions": [
                    {"id": "SEC-01", "prompt": "Does a revoked member in an old tab still get to approve?"},
                    {"id": "SEC-02", "prompt": "Can an urgent bank-detail message verify a payee without owner callback?"},
                    {"id": "SEC-03", "prompt": "Can invoice wording create approval or execution authority?"},
                    {"id": "SEC-04", "prompt": "Does an idempotent retry create a second receipt or state change?"},
                    {"id": "SEC-05", "prompt": "Does a payment delay invalidate the old mandate and require a fresh proposal?"},
                ],
                "summary": summarise_security(security),
                "participants": security,
            },
        },
    }


SME_CSV_HEADERS = [
    "participant_id", "role", "language", "experience_years", "business_profile", "prior_workflow", "model_status",
    *[field for task in ("t1", "t2", "t3", "t4", "t5") for field in (f"{task}_status", f"{task}_seconds")],
    *[f"sus{number}" for number in range(1, 11)], "sus_score", "overall_confidence",
    "most_useful_feature", "main_friction", "journey", "participant_reaction",
]

SECURITY_CSV_HEADERS = [
    "participant_id", "role", "security_familiarity", "work_context", "prior_security_habit",
    "confidence_before", "confidence_after",
    *[field for case in (case.lower().replace("-", "") for case in SECURITY_CASES)
      for field in (f"{case}_outcome", f"{case}_seconds", f"{case}_assistance", f"{case}_behavior")],
    "prompted_case_count", "initially_trusted_case_count", "participant_reaction",
]


def _sme_csv_row(participant: dict[str, object]) -> dict[str, object]:
    row: dict[str, object] = {
        "participant_id": participant["id"], "role": participant["role"], "language": participant["language"],
        "experience_years": participant["experience_years"], "business_profile": participant["business_profile"],
        "prior_workflow": participant["prior_workflow"], "model_status": participant["model_status"],
        "sus_score": participant["sus_score"], "overall_confidence": participant["overall_confidence"],
        "most_useful_feature": participant["most_useful_feature"], "main_friction": participant["main_friction"],
        "journey": " | ".join(participant["journey"]), "participant_reaction": participant["participant_reaction"],
    }
    for task_id in SME_TASKS:
        task = participant["tasks"][task_id]
        key = task_id.lower()
        row[f"{key}_status"] = task["status"]
        row[f"{key}_seconds"] = "" if task["seconds"] is None else task["seconds"]
    for number, value in enumerate(participant["sus_responses"], 1):
        row[f"sus{number}"] = value
    return row


def _security_csv_row(participant: dict[str, object]) -> dict[str, object]:
    row: dict[str, object] = {
        "participant_id": participant["id"], "role": participant["role"],
        "security_familiarity": participant["security_familiarity"], "work_context": participant["work_context"],
        "prior_security_habit": participant["prior_security_habit"],
        "confidence_before": participant["confidence_before"], "confidence_after": participant["confidence_after"],
        "prompted_case_count": participant["overall_behavior"]["prompted_cases"],
        "initially_trusted_case_count": participant["overall_behavior"]["initially_trusted_cases"],
        "participant_reaction": participant["participant_reaction"],
    }
    for case_id in SECURITY_CASES:
        key = case_id.lower().replace("-", "")
        result = participant["cases"][case_id]
        row[f"{key}_outcome"] = result["outcome"]
        row[f"{key}_seconds"] = result["seconds"]
        row[f"{key}_assistance"] = result["assistance"]
        row[f"{key}_behavior"] = result["behavior"]
    return row


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_dataset(dataset: dict[str, object]) -> None:
    """Fail loudly if a future edit stops producing two complete cohorts."""
    cohorts = dataset["cohorts"]
    sme = cohorts["sme"]["participants"]
    security = cohorts["security"]["participants"]
    if len(sme) != 20 or len(security) != 20:
        raise ValueError("The viewing dataset must contain exactly 20 SME and 20 security rows.")
    if len({item["id"] for item in sme}) != 20 or len({item["id"] for item in security}) != 20:
        raise ValueError("Participant IDs must be unique within each cohort.")
    for participant in sme:
        if len(participant["sus_responses"]) != 10:
            raise ValueError(f"{participant['id']} does not have a complete SUS response set.")
        if any(type(value) is not int or not 1 <= value <= 5 for value in participant["sus_responses"]):
            raise ValueError(f"{participant['id']} has an invalid SUS response.")
        for task_id in SME_TASKS:
            result = participant["tasks"][task_id]
            status = result["status"]
            seconds = result["seconds"]
            if status == "unavailable_model" and task_id != "T3":
                raise ValueError(f"Only T3 may be unavailable_model ({participant['id']}).")
            if status in {"completed", "assisted", "failed"} and not isinstance(seconds, int):
                raise ValueError(f"Attempted task {task_id} needs integer seconds ({participant['id']}).")
            if status not in {"completed", "assisted", "failed"} and seconds is not None:
                raise ValueError(f"Unattempted task {task_id} cannot have time ({participant['id']}).")
            if task_id == "T3" and status in {"completed", "assisted", "failed"} and participant["model_status"] != "available":
                raise ValueError(f"An attempted T3 needs an available model ({participant['id']}).")
    for participant in security:
        if set(participant["cases"]) != set(SECURITY_CASES):
            raise ValueError(f"{participant['id']} is missing a security case.")
        for case_id in SECURITY_CASES:
            result = participant["cases"][case_id]
            if result["seconds"] <= 0 or result["assistance"] not in {"unassisted", "prompted_once"}:
                raise ValueError(f"Invalid security result for {participant['id']} {case_id}.")


def write_dataset(output_dir: Path) -> dict[str, Path]:
    dataset = build_dataset()
    validate_dataset(dataset)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "synthetic-surveys.json"
    summary_path = output_dir / "summary.json"
    sme_csv_path = output_dir / "sme-survey.csv"
    security_csv_path = output_dir / "security-survey.csv"

    json_path.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {
        "schema_version": SCHEMA_VERSION,
        "evidence_status": dataset["evidence_status"],
        "disclaimer": dataset["disclaimer"],
        "cohorts": {
            "sme": dataset["cohorts"]["sme"]["summary"],
            "security": dataset["cohorts"]["security"]["summary"],
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_csv(sme_csv_path, SME_CSV_HEADERS, [_sme_csv_row(item) for item in dataset["cohorts"]["sme"]["participants"]])
    _write_csv(security_csv_path, SECURITY_CSV_HEADERS, [_security_csv_row(item) for item in dataset["cohorts"]["security"]["participants"]])
    return {
        "json": json_path,
        "summary": summary_path,
        "sme_csv": sme_csv_path,
        "security_csv": security_csv_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT, help="Directory for the viewing-only generated files")
    args = parser.parse_args()
    paths = write_dataset(args.out_dir.expanduser().resolve())
    print(f"Generated 20 SME rows and 20 security rows in {args.out_dir}")
    for path in paths.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
