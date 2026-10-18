"""Portable financial replay and source-aware judge challenges; never execution."""
from __future__ import annotations
from copy import deepcopy
import hashlib
from pathlib import Path

from .domain import (ValidationError, validate_business, validate_policy, validate_transaction,
                     validate_invoice, validate_bill, valid_date, canonical_json)
from .resilience import Context, digest, integer
from .projection import summary

VERSION = "decision-replay-v1"


def capsule_digest(value):
    """Browsers serialize 0.0 as 0; hash equivalent finite JSON numbers alike."""
    def normalise(item):
        if isinstance(item, dict):
            return {k: normalise(v) for k, v in item.items()}
        if isinstance(item, list):
            return [normalise(v) for v in item]
        if type(item) is float and item.is_integer():
            return int(item)
        return item
    return digest(normalise(value))


def engine_hashes():
    root = Path(__file__).resolve().parent
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file() and path.suffix in (".py", ".json") and "__pycache__" not in path.parts}


def export_capsule(context):
    if sum(len(rows) for rows in context.records.values()) > 300 or any(len(rows) > 150 for rows in context.records.values()):
        raise ValidationError("Replay export supports at most 300 records, 150 per kind.")
    if len({r["customer"] for r in context.records["invoices"]}) > 20:
        raise ValidationError("Replay supports at most 20 customers.")
    simulation = context.simulation()
    value = {"version": VERSION, "snapshot": context.snapshot, "target_date": context.target,
             "adjustments": context.adjustments, "engine_sha256": engine_hashes(),
             "expected_projection": summary(context.projection()),
             "expected_simulation": {k: simulation[k] for k in ("seed", "runs", "probability_breach", "minimum_cash_p10_minor", "probability_payroll_unfunded")},
             "privacy_note": "Contains this business's ledger and counterparty names. Keep private or use synthetic records. Self-hash detects edits, not a third-party signature."}
    return {**value, "capsule_sha256": capsule_digest(value)}


def replay_capsule(value):
    try:
        required = {"version", "snapshot", "target_date", "adjustments", "engine_sha256", "expected_projection", "expected_simulation", "privacy_note", "capsule_sha256"}
        if not isinstance(value, dict) or set(value) != required or value["version"] != VERSION:
            raise ValidationError("Unsupported replay capsule schema.")
        if len(canonical_json(value).encode()) > 1200000:
            raise ValidationError("Replay capsule is too large.")
        content = {k: v for k, v in value.items() if k != "capsule_sha256"}
        if capsule_digest(content) != value["capsule_sha256"]:
            raise ValidationError("Replay capsule integrity check failed.")
        snapshot = deepcopy(value["snapshot"])
        if set(snapshot) != {"business", "policy", "records", "state", "counterparties", "snapshot_hash"}:
            raise ValidationError("Invalid snapshot fields.")
        business = validate_business(snapshot["business"])
        identifier, currency = business["business_id"], business["currency"]
        validate_policy(snapshot["policy"], identifier, currency)
        records = snapshot["records"]
        if set(records) != {"transactions", "invoices", "bills"} or sum(len(v) for v in records.values()) > 300:
            raise ValidationError("Replay supports at most 300 records.")
        for kind, validator in (("transactions", validate_transaction), ("invoices", validate_invoice), ("bills", validate_bill)):
            if not isinstance(records[kind], list) or len(records[kind]) > 150:
                raise ValidationError("Replay supports at most 150 records of each kind.")
            for row in records[kind]:
                if not isinstance(row, dict) or not isinstance(row.get("risk_flags"), list) or len(row["risk_flags"]) > 20:
                    raise ValidationError("Invalid replay record.")
                checked = validator(row, identifier, currency)
                if checked["amount_minor"] != row["amount_minor"]:
                    raise ValidationError("Replay amounts must be integer minor units.")
        if len({r["customer"] for r in records["invoices"]}) > 20:
            raise ValidationError("Replay supports at most 20 customers.")
        state = snapshot["state"]
        if not isinstance(state["promises"], dict) or len(state["promises"]) > 150:
            raise ValidationError("Invalid replay promises.")
        for day in state["promises"].values():
            valid_date(day, "Promise date")
        valid_date(state["current_date"], "Simulation date")
        if (not isinstance(value["adjustments"], list) or len(value["adjustments"]) > 50
                or not all(isinstance(a, dict) for a in value["adjustments"])):
            raise ValidationError("Replay supports at most 50 adjustments.")
        if not isinstance(value["expected_simulation"], dict) or set(value["expected_simulation"]) != {
                "seed", "runs", "probability_breach", "minimum_cash_p10_minor", "probability_payroll_unfunded"}:
            raise ValidationError("Replay must include all financial simulation checks.")
        compatible = value["engine_sha256"] == engine_hashes()
        if not compatible:
            return {"read_only": True, "passed": False, "engine_compatible": False, "authenticated_origin": False,
                    "reason": "Engine or model bytes differ. Run with the capsule's original source version."}
        context = Context(snapshot, value["target_date"])
        context.adjustments = value["adjustments"]
        actual = summary(context.projection())
        simulated = context.simulation()
        actual_sim = {k: simulated[k] for k in value["expected_simulation"]}
        passed = actual == value["expected_projection"] and actual_sim == value["expected_simulation"]
        return {"version": VERSION, "read_only": True, "passed": passed, "engine_compatible": True,
                "authenticated_origin": False, "capsule_sha256": value["capsule_sha256"], "actual_projection": actual,
                "actual_simulation": actual_sim, "no_database_writes": True,
                "scope": "Recomputed deterministic financial outputs. The self-hash is not proof of authorship. No model generation, approval or payment is replayed."}
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("Malformed or unsupported replay capsule.") from exc


def challenge(lab, context, kind, customer=None, delay_days=7, bill_id=None, text=""):
    if kind == "delay":
        integer(delay_days, "Delay", 1, 60)
        if customer not in {r["customer"] for r in context.records["invoices"]}:
            raise ValidationError("Select a customer from this business.")
        return context.envelope({"kind": "challenge_delay", "customer": customer, "delay_days": delay_days,
                                 "before": summary(context.projection()), "after": summary(context.projection({customer: delay_days})),
                                 "scope": "Isolated scenario only; live records and approvals are unchanged."})
    if kind == "block_supplier":
        snapshot = deepcopy(context.snapshot)
        bill = next((b for b in snapshot["records"]["bills"] if b["id"] == bill_id), None)
        if not bill:
            raise ValidationError("Select a bill from this business.")
        bill["risk_flags"] = list(set(bill["risk_flags"] + ["payment_detail_change"]))
        result = lab.build_payload(snapshot, context.target, constraints=context.payload["owner_constraints"],
                                   excluded=sorted(set(context.payload.get("excluded_counterparties", []) + [bill["payee"]])))
        return context.envelope({"kind": "challenge_supplier", "blocked_supplier": bill["payee"],
                                 "proposal_preview": result, "scope": "Isolated planner preview. Nothing saved or approved."})
    if kind == "instruction":
        if not isinstance(text, str) or not 0 < len(text) <= 2000:
            raise ValidationError("Enter instruction text of 1-2000 characters.")
        from .screening import scan_text
        from .copilot import validate_plan
        try:
            validate_plan({"intent": "pay", "calls": [{"tool": "execute", "args": {}}]})
            blocked = False
        except ValidationError:
            blocked = True
        return context.envelope({"kind": "challenge_instruction", "rule_flags": scan_text(text),
                                 "forbidden_execution_tool_blocked": blocked, "model_called": False,
                                 "scope": "Text receives advisory rule screening; a separate fixed forbidden-tool attempt exercises the real typed permission guard. This is not a live-model prompt-injection benchmark."})
    raise ValidationError("Select delay, block_supplier or instruction challenge.")
