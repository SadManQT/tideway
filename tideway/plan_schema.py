"""Optional local-server generation constraints for the public copilot plan.

This schema improves output shape; it grants no permissions. Every generated
plan still passes copilot.validate_plan/preflight_plan, including role, exact
ledger-name, amount, currency, horizon and approval-boundary checks. Servers
which do not support JSON Schema must fail rather than silently retry loosely.
"""
from __future__ import annotations

import copy

from .copilot import MAX_CALLS, MAX_NAMES
from .domain import MAX_UNITS


def _object(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required),
            "additionalProperties": False}


def _text():
    return {"type": "string", "minLength": 1, "maxLength": 160}


def _names():
    return {"type": "array", "items": _text(), "maxItems": MAX_NAMES}


def _amount():
    return {"type": "number", "minimum": 0.01, "maximum": int(MAX_UNITS), "multipleOf": 0.01}


def _nullable(schema):
    # Only fields for which the existing tool validator treats None as omitted.
    return {"anyOf": [schema, {"type": "null"}]}


def _build_schema():
    args = {
        "project_cash": _object({"scenario": {"type": "string", "enum": ["base", "likely", "stress"]}}),
        "simulate_risk": _object({}),
        "reverse_stress": _object({}),
        "agreement_stress": _object({}),
        "recovery_options": _object({}),
        "what_if": _object({
            "customer_delays": _nullable({"type": "object", "maxProperties": MAX_NAMES,
                                "additionalProperties": {"type": "integer", "minimum": -30, "maximum": 90}}),
            "extra_expense": _nullable(_object({"amount": _amount(),
                                      "date": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                                      "currency": _text()}, ("amount", "date"))),
            "drop_invoice_customer": _nullable(_text()),
        }),
        "propose_plan": _object({"exclude_counterparties": _nullable(_names()),
                                  "max_discount_pct": _nullable({"type": "number", "minimum": 0, "maximum": 10, "multipleOf": 0.01}),
                                  "prefer": _nullable({"type": "string", "enum": ["lowest_cost", "lowest_risk", "fewest_asks"]})}),
        "explain_plan": _object({}),
        "credit_check": _object({"customer": _text(), "amount": _amount(),
                                  "terms_days": {"type": "integer", "minimum": 0, "maximum": 180},
                                  "currency": _text()}, ("customer", "amount", "terms_days")),
        "draft_reminders": _object({"customers": _nullable(_names())}),
        "bank_pack": _object({}),
        "customer_report": _object({"customer": _nullable(_text())}),
        "counterparty_risk": _object({}),
        "security_check": _object({}),
        "refuse": _object({"reason": {"type": "string", "enum": ["approve_or_move_money", "out_of_scope"]}}),
    }
    calls = [_object({"tool": {"type": "string", "const": tool}, "args": schema}, ("tool", "args"))
             for tool, schema in args.items()]
    return _object({"intent": _text(),
                    "calls": {"type": "array", "minItems": 1, "maxItems": MAX_CALLS,
                              "items": {"anyOf": calls}}}, ("intent", "calls"))


PLAN_SCHEMA = _build_schema()


def plan_schema(customer_names=None):
    """Return an independent schema, optionally closing names to a scoped ledger.

    Empty/unknown customer lists keep the generic typed map. The authoritative
    preflight still rejects names absent from that business. No text or inferred
    account details become permissions merely by appearing in this schema.
    """
    result = copy.deepcopy(PLAN_SCHEMA)
    if customer_names is None:
        return result
    names = list(dict.fromkeys(customer_names))
    if any(not isinstance(name, str) or not name.strip() or len(name) > 160 for name in names):
        raise ValueError("Scoped customer names must be non-empty strings of at most 160 characters.")
    if not names:
        return result
    branches = {branch["properties"]["tool"]["const"]: branch["properties"]["args"]["properties"]
                for branch in result["properties"]["calls"]["items"]["anyOf"]}
    customer = {**_text(), "enum": names}
    branches["credit_check"]["customer"] = copy.deepcopy(customer)
    branches["customer_report"]["customer"] = _nullable(copy.deepcopy(customer))
    branches["draft_reminders"]["customers"]["anyOf"][0]["items"] = copy.deepcopy(customer)
    branches["what_if"]["drop_invoice_customer"] = _nullable(copy.deepcopy(customer))
    branches["what_if"]["customer_delays"] = _nullable({
        "type": "object", "maxProperties": MAX_NAMES,
        "properties": {name: {"type": "integer", "minimum": -30, "maximum": 90} for name in names},
        "additionalProperties": False,
    })
    return result
