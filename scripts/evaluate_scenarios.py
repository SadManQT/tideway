"""Compare a fixed spreadsheet rule with Tideway on authored synthetic perturbations.

No cloud/model calls or financial mutations. These are variations of three demo
fixtures, not independent real SMEs or a held-out clinical/business study.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tideway import analytics, planner  # noqa: E402
from tideway.service import Tideway  # noqa: E402


def run():
    path = ROOT / "tests" / "fixtures" / "cash_scenarios.json"
    spec = json.loads(path.read_text(encoding="utf-8"))
    app = Tideway(":memory:")
    rows = []
    try:
        for case in spec["scenarios"]:
            snapshot = copy.deepcopy(app.store.snapshot(case["fixture"]))
            business, policy, records = (snapshot[k] for k in ("business", "policy", "records"))
            business["opening_cash_minor"] += case["cash_delta_minor"]
            derived = app.store.derived(snapshot)
            target = business["default_target_date"]
            seed = analytics.stable_seed(case["id"], "scenario-v1")
            common = {"basis_dates": derived["likely_dates"]}
            before = planner.evaluate_bundle(business, policy, records, target, [], **common)
            # Fixed before evaluation: defer the largest permitted bill by 14 days,
            # capped by policy, with no combination search or early-payment offer.
            eligible = []
            end = planner.horizon_end(business, target, policy["lookahead_days"])
            for bill in records["bills"]:
                options, _ = planner._deferral_options(business, policy, bill, end, derived["blocked"])
                eligible.extend(o for o in options if o["days"] == 14)
            baseline_actions = ([max(eligible, key=lambda o: o["amount_minor"])]
                                if eligible and not before["feasible"] else [])
            baseline = planner.evaluate_bundle(business, policy, records, target, baseline_actions, **common)
            plan = planner.plan_recovery(business, policy, records, target, profiles=derived["profiles"],
                                         blocked=derived["blocked"], mc_seed=seed, mc_runs=400, **common)
            selected = plan["bundles"][0] if plan["bundles"] else None
            actions = selected["actions"] if selected else []
            outcome = planner.evaluate_bundle(business, policy, records, target, actions, **common)
            rows.append({"id": case["id"], "fixture": case["fixture"], "cash_delta_minor": case["cash_delta_minor"],
                         "currency": business["currency"], "before_shortfall_minor": before["shortfall_minor"],
                         "spreadsheet_rule": {"feasible": baseline["feasible"], "payroll_ok": baseline["payroll_ok"],
                                              "shortfall_minor": baseline["shortfall_minor"],
                                              "economic_cost_minor": sum(a["economic_cost_minor"] for a in baseline_actions)},
                         "tideway": {"feasible": outcome["feasible"], "payroll_ok": outcome["payroll_ok"],
                                     "shortfall_minor": outcome["shortfall_minor"], "actions": len(actions),
                                     "honest_no_safe_plan": bool(plan["action_needed"] and not actions),
                                     "economic_cost_minor": sum(a["economic_cost_minor"] for a in actions),
                                     "risk_target_met": selected.get("risk_target_met") if selected else None}})
            print(f"{case['id']}: rule={baseline['feasible']} Tideway={outcome['feasible']}", flush=True)
    finally:
        app.store.close()
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "scenario_spec_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "cases": len(rows),
              "method": spec["method"], "rows": rows,
              "summary": {mode: {"feasible_cases": sum(r[mode]["feasible"] for r in rows),
                                  "payroll_funded_cases": sum(r[mode]["payroll_ok"] for r in rows)}
                          for mode in ("spreadsheet_rule", "tideway")},
              "limitations": ["Authored perturbations of three existing synthetic fixtures, not independent held-out SMEs.",
                              "Both methods use the same exact ledger evaluator; independent validation is not claimed.",
                              "The comparator is one stated simple rule, not Excel generally or a generic LLM.",
                              "No live model, real users, counterparty consent or realised cash improvement measured."]}
    out = ROOT / "evidence" / "scenario-comparison.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"]))
    return report


if __name__ == "__main__":
    run()
