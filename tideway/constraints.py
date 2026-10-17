"""Recorded owner instructions, independent of any model or planner implementation."""
from .domain import ValidationError

PREFERENCES = ("lowest_cost", "lowest_risk", "fewest_asks")


def owner_constraints(raw, policy):
    """Resolve the stricter ceiling; never invent missing legacy instructions.

    Old workspaces remain readable. A legacy proposal without recorded owner
    instructions must be replaced by an explicit new proposal before further
    approval, negotiation replacement or execution. No migration invents consent.
    """
    if not isinstance(raw, dict) or set(raw) != {"max_discount_bps", "prefer"}:
        raise ValidationError("Owner constraints are missing or invalid; create a fresh owner-reviewed proposal.")
    cap, prefer = raw["max_discount_bps"], raw["prefer"]
    if type(cap) is not int or not 0 <= cap <= 1000:
        raise ValidationError("Owner discount ceiling must be an integer from 0 to 1000 basis points.")
    if not isinstance(prefer, str) or prefer not in PREFERENCES:
        raise ValidationError("Owner preference must be lowest_cost, lowest_risk or fewest_asks.")
    return {"max_discount_bps": min(cap, policy["max_discount_bps"]), "prefer": prefer}


def check_plan_constraints(plan, policy):
    constraints = owner_constraints(plan.get("owner_constraints"), policy)
    excluded = plan.get("excluded_counterparties", [])
    if not isinstance(excluded, list) or any(not isinstance(name, str) or not name for name in excluded):
        raise ValidationError("Invalid owner counterparty exclusions.")
    for bundle in plan["bundles"]:
        for action in bundle["actions"]:
            if action["counterparty"] in excluded:
                raise ValidationError("Action violates the owner's counterparty exclusions.")
            if action["type"] == "early_payment_offer":
                bps = action.get("discount_bps")
                if type(bps) is not int or not 0 <= bps <= constraints["max_discount_bps"]:
                    raise ValidationError("Discount exceeds the owner or policy discount ceiling.")
    return constraints
