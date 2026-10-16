"""Recovery planning: candidate actions, an exact risk-aware optimiser and explanations.

The planner never moves money.  It proposes bundles of bounded actions that
counterparties may accept in the sandbox:

* supplier_deferral    - ask a supplier to move part or all of a bill later;
* early_payment_offer  - offer a customer a small discount to pay earlier;
* collection_reminder  - a zero-cash reminder draft (never counted as cash);
* mock financing       - labelled catalogue comparison, never executable.

Search: every combination of at most one option per record (bounded to the
most relevant records) is checked with a fast daily ledger.  A bundle is
feasible when it holds the reserve floor on every day of the planning horizon
(the target date plus a look-ahead, so a deferral cannot just push the
problem out of view) and payroll stays funded.  The cheapest feasible
bundles are then re-checked with the seeded Monte Carlo; the recommendation
is the cheapest bundle whose simulated breach probability is within the risk
target, otherwise the safest one.
"""
from __future__ import annotations

import itertools

from . import analytics
from .domain import OPEN_INVOICE_STATUSES, add_days, days_between, human_date, money_text
from .projection import build_events, horizon_end, project, summary
from .financing import CATALOGUE as FINANCING_CATALOGUE, compare as compare_financing


SUPPLIER_CREDIT_APR_BPS = 1200      # modelling assumption: asking a supplier to wait "costs" 12% a year
DEFERRAL_DAYS = (7, 14)
DEFERRAL_SHARES = (50, 100)
DISCOUNT_STEPS_BPS = (100, 200, 300)
MAX_GROUPS = 6
ROBUST_CANDIDATES = 40
RISK_TARGET = 0.10                  # recommended plans should breach in at most 2 of 20 simulated futures


def _round_up(value, step=100_000):
    return -(-value // step) * step if value > 0 else 0


def _deferral_options(business, policy, bill, end, blocked):
    if bill["status"] not in ("open", "scheduled") or bill.get("rescheduled_date"):
        return [], None
    if not business["opening_date"] <= bill["due_date"] <= end:
        return [], None
    if bill["priority"] == "payroll":
        return [], "POLICY_BLOCKED: payroll is protected and never deferred."
    if not bill["reschedule_allowed"]:
        return [], "POLICY_BLOCKED: the bill is marked as not reschedulable."
    if bill["id"] in blocked:
        return [], "SECURITY_BLOCKED: " + blocked[bill["id"]]
    options = []
    for days in DEFERRAL_DAYS:
        to_date = add_days(bill["due_date"], days)
        if days > policy["max_deferral_days"] or to_date > end:
            continue
        for share in DEFERRAL_SHARES:
            amount = min(bill["amount_minor"] * share // 100, policy["action_limit_minor"])
            if amount <= 0 or any(item["amount_minor"] == amount and item["days"] == days for item in options):
                continue
            cost = amount * days * SUPPLIER_CREDIT_APR_BPS // (365 * 10_000)
            options.append({
                "action_id": f"defer-{bill['id']}-{days}d-{amount}",
                "type": "supplier_deferral", "record_kind": "bill", "record_id": bill["id"],
                "counterparty": bill["payee"], "counterparty_kind": "supplier",
                "amount_minor": amount, "bill_amount_minor": bill["amount_minor"], "currency": business["currency"],
                "from_date": bill["due_date"], "to_date": to_date, "days": days,
                "economic_cost_minor": cost, "fee_minor": 0, "apr_equivalent_bps": SUPPLIER_CREDIT_APR_BPS,
                "requires_consent": True, "executable": True,
                "provenance": {"counterparty": f"ledger:bills/{bill['id']}.payee",
                               "amount_minor": f"ledger:bills/{bill['id']}.amount_minor x {share}% (capped by policy)",
                               "from_date": f"ledger:bills/{bill['id']}.due_date", "to_date": f"policy:max_deferral_days={policy['max_deferral_days']}"},
                "adjustment": {"kind": "bill_deferral", "bill_id": bill["id"], "amount_minor": amount,
                               "from_date": bill["due_date"], "to_date": to_date},
                "cost_note": f"No fee is charged. The implied cost uses a {SUPPLIER_CREDIT_APR_BPS / 100:.0f}% a year "
                             "supplier-credit assumption so deferrals compare fairly with discounts and financing.",
            })
    return options, None


def _early_payment_options(business, policy, invoice, expected, breach_date, end):
    if invoice["status"] not in OPEN_INVOICE_STATUSES or policy["max_discount_bps"] <= 0:
        return []
    if invoice["amount_minor"] > policy["action_limit_minor"]:
        return []
    anchor = breach_date or end
    pay_by = max(add_days(business["opening_date"], 2), add_days(anchor, -1))
    if pay_by >= expected or pay_by > end:
        return []
    accelerated = days_between(pay_by, expected)
    options = []
    for bps in DISCOUNT_STEPS_BPS:
        if bps > policy["max_discount_bps"]:
            continue
        discount = invoice["amount_minor"] * bps // 10_000
        options.append({
            "action_id": f"offer-{invoice['id']}-{bps}bps",
            "type": "early_payment_offer", "record_kind": "invoice", "record_id": invoice["id"],
            "counterparty": invoice["customer"], "counterparty_kind": "customer",
            "amount_minor": invoice["amount_minor"] - discount, "face_minor": invoice["amount_minor"],
            "discount_bps": bps, "discount_minor": discount, "currency": business["currency"],
            "from_date": expected, "to_date": pay_by, "days": accelerated,
            "apr_equivalent_bps": analytics.discount_apr_bps(bps, accelerated),
            "economic_cost_minor": discount, "fee_minor": 0, "requires_consent": True, "executable": True,
            "provenance": {"counterparty": f"ledger:invoices/{invoice['id']}.customer",
                           "face_minor": f"ledger:invoices/{invoice['id']}.amount_minor",
                           "discount_bps": f"policy:max_discount_bps={policy['max_discount_bps']}",
                           "to_date": "computed: one day before the first breach"},
            "adjustment": {"kind": "invoice_early_payment", "invoice_id": invoice["id"],
                           "face_minor": invoice["amount_minor"], "amount_minor": invoice["amount_minor"] - discount,
                           "to_date": pay_by},
            "cost_note": f"A {bps / 100:g}% discount for paying {accelerated} days earlier costs about "
                         f"{(analytics.discount_apr_bps(bps, accelerated) or 0) / 100:.0f}% a year.",
        })
    return options


class FastLedger:
    """Daily net-change array for quick feasibility checks of many bundles."""

    def __init__(self, business, policy, records, end, adjustments, invoice_dates, promises):
        self.start = business["opening_date"]
        self.length = days_between(self.start, end) + 1
        self.opening = business["opening_cash_minor"]
        self.reserve = policy["reserve_floor_minor"]
        events, _ = build_events(business, records, end, adjustments, invoice_dates, promises)
        self.net = [0] * self.length
        self.payroll = set()
        for event in events:
            index = days_between(self.start, event["date"])
            self.net[index] += event["effect_minor"]
            if event.get("payroll"):
                self.payroll.add(index)
        self.invoice_dates = {event["id"]: event["date"] for event in events if event["kind"] == "invoice"}

    def index(self, day):
        offset = days_between(self.start, day)
        return offset if 0 <= offset < self.length else None

    def deltas(self, option):
        changes = []
        if option["type"] == "supplier_deferral":
            for day, effect in ((option["from_date"], option["amount_minor"]), (option["to_date"], -option["amount_minor"])):
                index = self.index(day)
                if index is not None:
                    changes.append((index, effect))
        elif option["type"] == "early_payment_offer":
            current = self.invoice_dates.get(option["record_id"])
            if current is not None:
                changes.append((self.index(current), -option["face_minor"]))
            index = self.index(option["to_date"])
            if index is not None:
                changes.append((index, option["amount_minor"]))
        elif option["type"] == "shift_invoice":
            current = self.invoice_dates.get(option["record_id"])
            for day, effect in ((current, -option["amount_minor"]), (option["to_date"], option["amount_minor"])):
                index = self.index(day) if day else None
                if index is not None:
                    changes.append((index, effect))
        return changes

    def evaluate(self, changes):
        net = self.net[:]
        for index, effect in changes:
            net[index] += effect
        balance = minimum = self.opening
        payroll_ok = True
        for index, change in enumerate(net):
            balance += change
            if balance < minimum:
                minimum = balance
            if index in self.payroll and balance < 0:
                payroll_ok = False
        return {"minimum_cash_minor": minimum, "shortfall_minor": max(0, self.reserve - minimum), "payroll_ok": payroll_ok}


def message_for(option, business_name):
    amount = money_text(option["amount_minor"], option["currency"])
    if option["type"] == "supplier_deferral":
        return (f"Hello {option['counterparty']}, this is {business_name}. Could we move {amount} of bill "
                f"{option['record_id']} from {human_date(option['from_date'], True)} to {human_date(option['to_date'], True)}? The rest of the bill "
                f"stays on schedule. Please reply to accept or propose different terms.")
    if option["type"] == "early_payment_offer":
        return (f"Hello {option['counterparty']}, this is {business_name}. If invoice {option['record_id']} "
                f"({money_text(option['face_minor'], option['currency'])}) is paid by {human_date(option['to_date'], True)}, we will accept "
                f"{amount} as full settlement ({option['discount_bps'] / 100:g}% early-payment discount).")
    return option.get("message", "")


def reminder_for(invoice, profile, business_name, late_share=None):
    grade = (profile or {}).get("grade", "B")
    tone = {"A": "friendly", "B": "polite", "C": "firm", "D": "firm"}[grade]
    opener = {"friendly": "Just a friendly reminder", "polite": "A polite reminder",
              "firm": "Please treat this as a priority reminder"}[tone]
    amount = money_text(invoice["amount_minor"], invoice["currency"])
    text = (f"Hello {invoice['customer']}, this is {business_name}. {opener} that invoice {invoice['id']} for {amount} "
            f"is due on {human_date(invoice['due_date'], True)}. Could you confirm the date you expect to pay?")
    if grade == "D":
        text += " If there is a problem, we are open to an instalment plan."
    return {"action_id": f"remind-{invoice['id']}", "type": "collection_reminder", "record_kind": "invoice",
            "record_id": invoice["id"], "counterparty": invoice["customer"], "counterparty_kind": "customer",
            "amount_minor": invoice["amount_minor"], "currency": invoice["currency"], "tone": tone, "grade": grade,
            "from_date": invoice["expected_collection_date"], "to_date": invoice["due_date"], "days": 0,
            "late_risk": late_share, "economic_cost_minor": 0, "cash_effect_minor": 0,
            "requires_consent": False, "executable": True, "message": text,
            "cost_note": "A reminder is a message. It is never counted as collected cash."}


def plan_recovery(business, policy, records, target_date, *, accepted=(), promises=None, profiles=None,
                  basis_dates=None, basis="likely", blocked=None, excluded_counterparties=(),
                  mc_seed=0, mc_runs=400, late_share=None, as_of=None, prefer="lowest_cost"):
    """Compare recovery bundles for one business and target date."""
    blocked = dict(blocked or {})
    excluded = set(excluded_counterparties)
    end = horizon_end(business, target_date, policy["lookahead_days"])
    accepted = list(accepted)
    dates = basis_dates if basis != "base" else None
    common = {"adjustments": accepted, "promises": promises, "lookahead_days": policy["lookahead_days"]}
    baseline = project(business, policy, records, target_date, scenario="base", **common)
    basis_projection = project(business, policy, records, target_date, scenario=basis, invoice_dates=dates, **common)
    breach = basis_projection["first_breach_date"]
    ledger = FastLedger(business, policy, records, end, accepted, dates, promises)
    adjusted_bills = {item["bill_id"] for item in accepted if item["kind"] == "bill_deferral"}
    adjusted_invoices = {item["invoice_id"] for item in accepted if item["kind"] == "invoice_early_payment"}
    groups, rejected = [], []
    for bill in records["bills"]:
        if bill["id"] in adjusted_bills:
            continue
        if bill["payee"] in excluded:
            rejected.append({"record_id": bill["id"], "counterparty": bill["payee"], "code": "DECLINED",
                             "reason": "The supplier declined in this sandbox; re-planned without them."})
            continue
        options, reason = _deferral_options(business, policy, bill, end, blocked)
        if reason:
            code, _, text = reason.partition(": ")
            rejected.append({"record_id": bill["id"], "counterparty": bill["payee"], "code": code, "reason": text})
        if options:
            groups.append(options)
    for invoice in records["invoices"]:
        if invoice["id"] in adjusted_invoices or invoice["status"] not in OPEN_INVOICE_STATUSES:
            continue
        if invoice["customer"] in excluded:
            rejected.append({"record_id": invoice["id"], "counterparty": invoice["customer"], "code": "DECLINED",
                             "reason": "The customer declined in this sandbox; re-planned without them."})
            continue
        # Price acceleration from the date cash is actually expected (likely or promised), even when that
        # date falls after the horizon and so has no event in the ledger.
        expected = ledger.invoice_dates.get(invoice["id"]) or (dates or {}).get(invoice["id"]) or invoice["expected_collection_date"]
        if (promises or {}).get(invoice["id"]):
            expected = max(promises[invoice["id"]], expected)
        options = _early_payment_options(business, policy, invoice, expected, breach, end)
        if options:
            groups.append(options)
    groups.sort(key=lambda options: -max(option.get("face_minor", option["amount_minor"]) for option in options))
    groups = groups[:MAX_GROUPS]
    for options in groups:
        for option in options:
            option["deltas"] = ledger.deltas(option)
    none_result = ledger.evaluate([])
    action_needed = none_result["shortfall_minor"] > 0 or not none_result["payroll_ok"]
    evaluated = []
    for choice in itertools.product(*[[None] + options for options in groups]):
        chosen = [option for option in choice if option is not None]
        if not chosen:
            continue
        exposure = sum(option.get("face_minor", option["amount_minor"]) for option in chosen)
        if exposure > policy["daily_cap_minor"]:
            continue
        result = ledger.evaluate([delta for option in chosen for delta in option["deltas"]])
        feasible = result["shortfall_minor"] == 0 and result["payroll_ok"]
        evaluated.append({"feasible": feasible, "shortfall": result["shortfall_minor"],
                          "cost": sum(option["economic_cost_minor"] for option in chosen),
                          "counterparties": len({option["counterparty"] for option in chosen}),
                          "exposure": exposure, "chosen": chosen})
    evaluated.sort(key=lambda item: (not item["feasible"], item["shortfall"], item["cost"], item["counterparties"], item["exposure"]))
    feasible = [item for item in evaluated if item["feasible"]] if action_needed else []

    def robust(item):
        adjustments = accepted + [option["adjustment"] for option in item["chosen"]]
        simulation = analytics.monte_carlo(business, policy, records, target_date, adjustments, promises,
                                           runs=mc_runs, seed=mc_seed, lookahead_days=policy["lookahead_days"], as_of=as_of)
        item["probability_breach"] = simulation["probability_breach"]
        item["futures_short_of_20"] = simulation["futures_short_of_20"]
        return item

    shortlist = [robust(item) for item in feasible[:ROBUST_CANDIDATES]]
    # Monte Carlo has sampling noise (about +/-2 points at 400 runs), so risks
    # are compared in 5-point buckets (one simulated future in twenty).
    bucket = lambda item: round(item["probability_breach"] / 0.05)  # noqa: E731
    within = [item for item in shortlist if item["probability_breach"] <= RISK_TARGET]
    if prefer == "lowest_risk":
        ranked = sorted(shortlist, key=lambda item: (bucket(item), item["cost"], item["counterparties"]))
    elif prefer == "fewest_asks":
        ranked = sorted(within, key=lambda item: (item["counterparties"], item["cost"])) + sorted(
            (item for item in shortlist if item not in within), key=lambda item: (bucket(item), item["counterparties"], item["cost"]))
    else:
        ranked = within + sorted((item for item in shortlist if item not in within),
                                 key=lambda item: (bucket(item), item["cost"], item["counterparties"]))
    selected = []
    by_cost = sorted(shortlist, key=lambda item: (item["cost"], item["counterparties"]))
    names = lambda item: frozenset(option["counterparty"] for option in item["chosen"])  # noqa: E731
    ordered = ranked[:1] + by_cost[:1] + [item for item in ranked[1:] if names(item) not in {names(i) for i in ranked[:1] + by_cost[:1]}] + ranked[1:]
    for item in ordered:
        ids = {option["action_id"] for option in item["chosen"]}
        # Skip duplicates and plans that only add actions to one already shown (dominated).
        if any(ids >= {option["action_id"] for option in other["chosen"]} for other in selected):
            continue
        selected.append(item)
        if len(selected) == 3:
            break
    if not selected and action_needed and evaluated:
        selected = [robust(evaluated[0])]  # best partial plan: honest, flagged infeasible
    business_name = business.get("name", "the business")
    bundles = []
    for rank, item in enumerate(selected):
        adjustments = accepted + [option["adjustment"] for option in item["chosen"]]
        after = project(business, policy, records, target_date, scenario=basis, invoice_dates=dates,
                        adjustments=adjustments, promises=promises, lookahead_days=policy["lookahead_days"])
        after_base = project(business, policy, records, target_date, scenario="base", adjustments=adjustments,
                             promises=promises, lookahead_days=policy["lookahead_days"])
        actions = []
        for option in item["chosen"]:
            action = {key: value for key, value in option.items() if key != "deltas"}
            action["message"] = message_for(option, business_name)
            others = [delta for other in item["chosen"] if other is not option for delta in other["deltas"]]
            action["shortfall_without_minor"] = ledger.evaluate(others)["shortfall_minor"]
            actions.append(action)
        bundles.append({
            "bundle_id": "recommended" if rank == 0 else f"alternative-{rank}",
            "feasible": item["feasible"], "actions": actions,
            "economic_cost_minor": item["cost"], "counterparties": item["counterparties"], "exposure_minor": item["exposure"],
            "probability_breach_after": item.get("probability_breach"),
            "futures_short_of_20_after": item.get("futures_short_of_20"),
            "risk_target_met": item.get("probability_breach") is not None and item["probability_breach"] <= RISK_TARGET,
            "dual_approval_required": item["exposure"] > policy["dual_approval_threshold_minor"],
            "after": summary(after), "after_base": summary(after_base),
            "remaining_shortfall_minor": after["reserve_shortfall_minor"],
        })
    recommended = bundles[0] if bundles else None
    for bundle in bundles[1:]:
        if bundle["probability_breach_after"] is not None and recommended["probability_breach_after"] is not None \
                and round(bundle["probability_breach_after"] / 0.05) > round(recommended["probability_breach_after"] / 0.05):
            bundle["why_not"] = (f"RISKIER: {round(bundle['probability_breach_after'] * 100)}% of simulated futures still breach "
                                 f"(about {bundle['futures_short_of_20_after']} in 20) versus "
                                 f"{round(recommended['probability_breach_after'] * 100)}% for the recommendation.")
        else:
            delta = bundle["economic_cost_minor"] - recommended["economic_cost_minor"]
            bundle["why_not"] = f"COSTLIER: {money_text(max(0, delta), business['currency'])} more in economic cost."
    singles, why_not = [], []
    chosen_ids = {action["action_id"] for action in (recommended or {}).get("actions", [])}
    for options in groups:
        for option in options:
            result = ledger.evaluate(option["deltas"])
            holds = result["shortfall_minor"] == 0 and result["payroll_ok"]
            singles.append({"action_id": option["action_id"], "type": option["type"], "counterparty": option["counterparty"],
                            "economic_cost_minor": option["economic_cost_minor"],
                            "remaining_shortfall_minor": result["shortfall_minor"], "holds_reserve_alone": holds})
            if option["action_id"] in chosen_ids or not action_needed:
                continue
            if holds and recommended and option["economic_cost_minor"] >= recommended["economic_cost_minor"]:
                code = f"COSTLIER: works alone but costs {money_text(option['economic_cost_minor'], business['currency'])}."
            elif holds:
                code = "RISKIER: works on the likely path but fails more simulated futures."
            else:
                code = f"INSUFFICIENT_ALONE: still {money_text(result['shortfall_minor'], business['currency'])} short."
            why_not.append({"action_id": option["action_id"], "counterparty": option["counterparty"],
                            "type": option["type"], "reason": code})
    levers = [{"kind": "single_action", "text": _describe(next(o for g in groups for o in g if o["action_id"] == item["action_id"])),
               "economic_cost_minor": item["economic_cost_minor"]}
              for item in singles if item["holds_reserve_alone"]][:4]
    for invoice in records["invoices"]:
        current = ledger.invoice_dates.get(invoice["id"])
        if invoice["status"] in OPEN_INVOICE_STATUSES and current and current > invoice["due_date"] and action_needed:
            result = ledger.evaluate(ledger.deltas({"type": "shift_invoice", "record_id": invoice["id"],
                                                    "amount_minor": invoice["amount_minor"], "to_date": invoice["due_date"]}))
            if result["shortfall_minor"] == 0 and result["payroll_ok"]:
                levers.append({"kind": "customer_on_time", "economic_cost_minor": 0,
                               "text": f"{invoice['customer']} pays invoice {invoice['id']} on its due date ({human_date(invoice['due_date'])})"})
    gap = basis_projection["reserve_shortfall_minor"]
    financing = compare_financing(business, policy, records, target_date, gap, breach, as_of=as_of,
                                  adjustments=accepted, invoice_dates=dates, promises=promises)
    customer_profiles = (profiles or {}).get("customers", {})
    offered = {action["record_id"] for action in (recommended or {}).get("actions", []) if action["type"] == "early_payment_offer"}
    open_invoices = [row for row in records["invoices"] if row["status"] in OPEN_INVOICE_STATUSES
                     and row["id"] not in offered and row["id"] not in adjusted_invoices]
    late_share = late_share or {}
    open_invoices.sort(key=lambda row: (-(late_share.get(row["id"], 0) * row["amount_minor"]), -row["amount_minor"], row["id"]))
    reminders = [reminder_for(row, customer_profiles.get(row["customer"]), business_name, late_share.get(row["id"]))
                 for row in open_invoices[:3]]
    return {"business_id": business["business_id"], "target_date": target_date, "currency": business["currency"],
            "basis": basis, "planning_horizon_end": end, "risk_target": RISK_TARGET,
            "baseline": summary(baseline), "basis_projection": summary(basis_projection),
            "gap_minor": gap, "action_needed": action_needed,
            "bundles": bundles, "single_option_checks": singles, "why_not": why_not, "levers": levers,
            "financing": financing, "reminders": reminders, "rejected": rejected,
            "explanation": explain(business, basis, basis_projection, bundles, financing, levers, action_needed),
            "search": {"records_considered": len(groups), "combinations_evaluated": len(evaluated),
                       "robustness_checked": len(shortlist), "monte_carlo_runs_each": mc_runs,
                       "objective": "Hold the reserve floor every day through the planning horizon with payroll funded; "
                                    f"prefer bundles that breach in at most {round(RISK_TARGET * 20)} of 20 simulated futures; "
                                    "then minimise economic cost and the number of counterparties asked."},
            "assumptions": {"supplier_credit_apr_bps": SUPPLIER_CREDIT_APR_BPS, "deferral_days": list(DEFERRAL_DAYS),
                            "discount_steps_bps": list(DISCOUNT_STEPS_BPS), "reminders_are_not_collections": True,
                            "financing_is_mock": True}}


def evaluate_bundle(business, policy, records, target_date, actions, *, accepted=(), promises=None, basis_dates=None):
    """Feasibility of a fixed bundle (used for counter-offers)."""
    end = horizon_end(business, target_date, policy["lookahead_days"])
    ledger = FastLedger(business, policy, records, end, list(accepted), basis_dates, promises)
    result = ledger.evaluate([delta for action in actions for delta in ledger.deltas(action)])
    return {"feasible": result["shortfall_minor"] == 0 and result["payroll_ok"], **result}


def explain(business, basis, basis_projection, bundles, financing, levers, action_needed):
    currency = business["currency"]
    view = {"likely": "customers' usual payment habits", "base": "the schedule", "stress": "slow-payment stress"}.get(basis, basis)
    if not action_needed:
        return f"No action needed: based on {view}, cash stays at or above the reserve floor through the planning horizon."
    lines = [f"Without action, based on {view}, cash falls to {money_text(basis_projection['minimum_cash_minor'], currency)} "
             f"on {human_date(basis_projection['minimum_cash_date'])}: {money_text(basis_projection['reserve_shortfall_minor'], currency)} "
             f"below the reserve floor."]
    if not bundles:
        lines.append("No supplier deferral or early-payment offer is available within policy.")
    elif bundles[0]["feasible"]:
        best = bundles[0]
        lines.append("Recommended: " + "; ".join(_describe(action) for action in best["actions"]) +
                     f". Economic cost {money_text(best['economic_cost_minor'], currency)}; "
                     f"{best['counterparties']} counterpart{'y' if best['counterparties'] == 1 else 'ies'} must agree; "
                     f"{best['futures_short_of_20_after']} of 20 simulated futures still breach.")
        if not any(lever["kind"] == "single_action" for lever in levers):
            lines.append("No single action is enough on its own, so the plan combines actions.")
    else:
        lines.append(f"No safe combination exists within policy. The strongest leaves "
                     f"{money_text(bundles[0]['remaining_shortfall_minor'], currency)} uncovered; escalate to the owner.")
    cheapest = min((item for item in financing if item["feasible"]), key=lambda item: item["fee_minor"], default=None)
    if cheapest:
        lines.append(f"For comparison only, {cheapest['label']} would cost {money_text(cheapest['fee_minor'], currency)} "
                     f"in fees (about {cheapest['apr_bps'] / 100:.0f}% a year).")
    return " ".join(lines)


def _describe(action):
    amount = money_text(action["amount_minor"], action["currency"])
    if action["type"] == "supplier_deferral":
        return f"ask {action['counterparty']} to move {amount} from {human_date(action['from_date'])} to {human_date(action['to_date'])}"
    if action["type"] == "early_payment_offer":
        return (f"offer {action['counterparty']} {action['discount_bps'] / 100:g}% off to pay "
                f"{money_text(action['face_minor'], action['currency'])} by {human_date(action['to_date'])}")
    return action["type"]
