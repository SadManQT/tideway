"""Treasury hub: reconciliation with the projection engine, determinism, scan recall and passport integrity."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from tideway.domain import canonical_json
from tideway.projection import project
from tideway.service import Tideway
from tideway import treasury
from tideway.treasury import Treasury

BUSINESSES = ("shapla-services", "lotus-print", "harbourline-traders")
OWNER = {"id": "nadia", "name": "Nadia Rahman", "role": "owner"}


class TreasuryCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tideway = Tideway(":memory:")
        cls.store = cls.tideway.store
        cls.treasury = Treasury(cls.tideway)

    @classmethod
    def tearDownClass(cls):
        cls.store.close()

    def context(self, business_id):
        snapshot = self.store.snapshot(business_id)
        return snapshot, self.store.derived(snapshot)

    # ---- 13-week cash flow -------------------------------------------------------------

    def test_week_13_closing_and_daily_minimum_reconcile_with_projection_engine(self):
        for business_id in BUSINESSES:
            snapshot, derived = self.context(business_id)
            plan = treasury.twcf(snapshot, derived)
            business, policy, records, state = (snapshot["business"], snapshot["policy"], snapshot["records"], snapshot["state"])
            end = treasury.add_days(business["opening_date"], 90)
            self.assertEqual(plan["end_date"], end)
            for name, dates in (("scheduled", None), ("likely", derived["likely_dates"]), ("stress", derived["stress_dates"])):
                with self.subTest(business=business_id, scenario=name):
                    engine = project(business, policy, records, end, adjustments=state["adjustments"],
                                     invoice_dates=dates, promises=state["promises"], lookahead_days=0)
                    weeks = plan["scenarios"][name]["weeks"]
                    totals = plan["scenarios"][name]["totals"]
                    self.assertEqual(len(weeks), 13)
                    self.assertEqual(weeks[-1]["closing_cash_minor"], engine["closing_cash_minor"])
                    self.assertEqual(min(business["opening_cash_minor"], *(w["lowest_cash_minor"] for w in weeks)),
                                     engine["minimum_cash_minor"])
                    self.assertEqual(totals["lowest_cash_minor"], engine["minimum_cash_minor"])
                    self.assertEqual(totals["receipts_minor"], engine["total_inflow_minor"])
                    self.assertEqual(totals["disbursements_minor"], engine["total_outflow_minor"])
                    # Each week opens where the previous one closed and nets exactly.
                    opening = business["opening_cash_minor"]
                    for week in weeks:
                        self.assertEqual(week["opening_cash_minor"], opening)
                        self.assertEqual(week["opening_cash_minor"] + week["receipts_minor"] - week["disbursements_minor"],
                                         week["closing_cash_minor"])
                        self.assertEqual(week["receipts_minor"], sum(item["amount_minor"] for item in week["receipts_by_customer"])
                                         + week["other_receipts_minor"])
                        self.assertEqual(week["disbursements_minor"], week["supplier_bills_minor"] + week["payroll_minor"]
                                         + week["other_disbursements_minor"])
                        self.assertEqual(week["below_reserve"], week["lowest_cash_minor"] < policy["reserve_floor_minor"])
                        opening = week["closing_cash_minor"]
                    self.assertTrue(plan["scenarios"][name]["reconciliation"]["matches"])

    def test_twcf_days_match_the_dashboard_projections_on_the_shared_horizon(self):
        for business_id in BUSINESSES:
            snapshot, derived = self.context(business_id)
            plan = treasury.twcf(snapshot, derived)
            analysis = self.tideway.analysis(business_id)
            for name, key in (("scheduled", "base"), ("likely", "likely"), ("stress", "stress")):
                dashboard = {day["date"]: day["closing_cash_minor"] for day in analysis["projections"][key]["days"]}
                shared = [day for day in plan["scenarios"][name]["daily"] if day["date"] in dashboard]
                self.assertGreater(len(shared), 30)
                for day in shared:
                    self.assertEqual(day["closing_cash_minor"], dashboard[day["date"]], (business_id, name, day["date"]))

    def test_weeks_below_reserve_are_highlighted_for_the_payroll_gap(self):
        plan = self.treasury.twcf("shapla-services")
        likely = plan["scenarios"]["likely"]["totals"]
        self.assertTrue(likely["weeks_below_reserve"])
        self.assertEqual(likely["first_week_below_reserve"], likely["weeks_below_reserve"][0])
        self.assertLess(likely["lowest_cash_minor"], plan["reserve_floor_minor"])

    def test_outputs_are_deterministic_and_read_only(self):
        for business_id in BUSINESSES:
            before = self.store.snapshot(business_id)["snapshot_hash"]
            entries = len(self.store.evidence(business_id)["entries"])
            first = (self.treasury.twcf(business_id), self.treasury.health(business_id), self.treasury.scan(business_id, True))
            second = (self.treasury.twcf(business_id), self.treasury.health(business_id), self.treasury.scan(business_id, True))
            self.assertEqual(canonical_json(first), canonical_json(second))
            self.assertEqual(self.store.snapshot(business_id)["snapshot_hash"], before)
            self.assertEqual(len(self.store.evidence(business_id)["entries"]), entries)
            self.assertFalse(any(row["id"].startswith("syn-") for row in self.store.records(business_id)["bills"]))

    # ---- health score ------------------------------------------------------------------

    def test_health_score_is_the_documented_weighted_mean(self):
        self.assertEqual(sum(treasury.HEALTH_WEIGHTS.values()), 100)
        for business_id in BUSINESSES:
            result = self.treasury.health(business_id)
            available = [c for c in result["components"] if c["available"]]
            weight = sum(c["weight"] for c in available)
            expected = round(sum(c["weight"] * c["score"] for c in available) / weight)
            self.assertEqual(result["score"], expected)
            self.assertTrue(0 <= result["score"] <= 100)
            for component in result["components"]:
                self.assertTrue(component["formula"])
                if component["available"]:
                    self.assertTrue(0 <= component["score"] <= 100)
            self.assertLessEqual(len(result["suggestions"]), 3)
            gains = [item["max_gain_points"] for item in result["suggestions"]]
            self.assertEqual(gains, sorted(gains, reverse=True))
            self.assertEqual({c["id"] for c in result["components"]}, set(treasury.HEALTH_WEIGHTS))

    def test_breach_component_uses_the_seeded_monte_carlo(self):
        snapshot, derived = self.context("lotus-print")
        simulation = treasury._simulation(snapshot)
        result = treasury.health(snapshot, derived)
        breach = next(c for c in result["components"] if c["id"] == "breach_risk")
        self.assertEqual(breach["value"], simulation["probability_breach"])
        self.assertEqual(breach["score"], round(100 * (1 - simulation["probability_breach"])))

    # ---- payment-integrity scan ------------------------------------------------------------

    def test_scan_finds_every_planted_anomaly_and_no_clean_control(self):
        for business_id in BUSINESSES:
            result = self.treasury.scan(business_id, True)["synthetic_sample"]
            with self.subTest(business=business_id):
                self.assertEqual(result["recall"], 1.0)
                self.assertTrue(all(label["detected"] for label in result["labels"]))
                self.assertEqual(result["false_positives"], 0)
                self.assertEqual(result["precision"], 1.0)
                self.assertEqual(result["clean_bills_flagged"], [])
                self.assertEqual({label["rule"] for label in result["labels"]}, {rule["rule"] for rule in treasury.RULES})

    def test_ledger_scan_surfaces_existing_payee_flags_and_blocks_nothing(self):
        result = self.treasury.scan("harbourline-traders")
        self.assertIsNone(result["synthetic_sample"])
        rules = {(f["rule"], tuple(f["bill_ids"])) for f in result["ledger_findings"]}
        self.assertIn(("bank_details_changed", ("bill-harbour-straits-oct",)), rules)
        self.assertIn(("lookalike_payee", ("bill-harbour-lookalike-oct",)), rules)
        derived = self.context("harbourline-traders")[1]
        flagged = {f["bill_ids"][0] for f in result["ledger_findings"] if f["rule"] in ("bank_details_changed", "lookalike_payee")}
        self.assertEqual(flagged, set(derived["blocked"]))
        self.assertTrue(all(f["blocks_nothing"] for f in result["ledger_findings"]))
        text = json.dumps(result)
        self.assertNotIn("AC-9907-0001", text)  # bank accounts are masked

    def test_scan_rules_on_handmade_bills(self):
        def bill(i, payee, amount, day, status="open", description="Invoice", account="AC-0000-0001"):
            return {"id": f"b{i}", "payee": payee, "payee_account": account, "amount_minor": amount,
                    "due_date": f"2026-10-{day:02d}", "status": status, "description": description}
        findings = treasury.run_rules([bill(1, "Acme Ltd", 123_456, 1), bill(2, "ACME", 123_456, 6)], 1_000_000, "BDT", {})
        self.assertEqual([(f["rule"], f["bill_ids"]) for f in findings], [("duplicate_bill", ["b1", "b2"])])
        findings = treasury.run_rules([bill(1, "Acme", 123_456, 1), bill(2, "Acme", 123_456, 20)], 1_000_000, "BDT", {})
        self.assertEqual(findings, [])  # monthly repeat, outside the window
        findings = treasury.run_rules([bill(1, "Acme", 111_111, 1, description="Ref INV-2291"),
                                       bill(2, "Acme", 222_222, 25, description="INV 2291 copy")], 1_000_000, "BDT", {})
        self.assertEqual([f["rule"] for f in findings], ["duplicate_bill"])
        findings = treasury.run_rules([bill(1, "Acme", 600_001, 1), bill(2, "Acme", 500_003, 3)], 1_000_000, "BDT", {})
        self.assertEqual([f["rule"] for f in findings], ["split_below_threshold"])
        findings = treasury.run_rules([bill(1, "Acme", 600_001, 1), bill(2, "Acme", 500_003, 3)], None, "BDT", {})
        self.assertEqual(findings, [])
        with self.assertRaises(Exception):
            self.treasury.scan("shapla-services", "yes")

    # ---- credit passport ---------------------------------------------------------------

    def test_passport_verifies_and_survives_a_json_round_trip(self):
        issued = self.treasury.issue_passport("shapla-services", OWNER, "operator:nadia")
        document = json.loads(json.dumps(issued["passport"]))
        result = self.treasury.verify_passport("shapla-services", document)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["issuance_logged"])
        self.assertFalse(result["records_changed_since_issue"])
        for key in treasury.PASSPORT_FIELDS:
            self.assertIn(key, document)
        self.assertFalse(any(isinstance(value, float) for value in _leaves(document)))
        entries = self.store.evidence("shapla-services")["entries"]
        self.assertEqual(entries[-1]["action"], "treasury.passport.issue")
        self.assertEqual(entries[-1]["details"]["passport_id"], document["passport_id"])
        self.assertEqual(issued["audit"]["audit_hash"], entries[-1]["entry_hash"])

    def test_passport_tamper_wrong_business_expiry_and_malformed_are_rejected(self):
        document = self.treasury.issue_passport("lotus-print", OWNER, "operator:nadia")["passport"]
        for path, value in ((("health", "score"), 99), (("twcf", "likely", "closing_cash_minor"), 10**9),
                            (("business", "business_id"), "shapla-services"), (("expires_at",), "2099-01-01T00:00:00+00:00")):
            copy = json.loads(json.dumps(document))
            target = copy
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = value
            result = self.treasury.verify_passport("lotus-print", copy)
            self.assertFalse(result["valid"], path)
            self.assertEqual(result["reason"], "signature_mismatch", path)
        self.assertEqual(self.treasury.verify_passport("shapla-services", document)["reason"], "wrong_business")
        later = datetime.now(timezone.utc) + timedelta(days=31)
        self.assertEqual(self.treasury.verify_passport("lotus-print", document, now=later)["reason"], "expired")
        old = self.treasury.issue_passport("lotus-print", OWNER, "operator:nadia",
                                           now=datetime.now(timezone.utc) - timedelta(days=40))["passport"]
        self.assertEqual(self.treasury.verify_passport("lotus-print", old)["reason"], "expired")
        extra = {**document, "note": "added"}
        self.assertEqual(self.treasury.verify_passport("lotus-print", extra)["reason"], "malformed")
        for bad in (None, [], "passport", {"signature": "0" * 64}):
            self.assertEqual(self.treasury.verify_passport("lotus-print", bad)["reason"], "malformed")

    def test_passport_key_is_separate_from_the_mandate_key(self):
        document = self.treasury.issue_passport("harbourline-traders", OWNER, "operator:nadia")["passport"]
        self.assertFalse(self.store.verify_mandate_document(document)["signature_valid"])
        other = Tideway(":memory:")
        try:
            self.assertEqual(Treasury(other).verify_passport("harbourline-traders", document)["reason"], "signature_mismatch")
        finally:
            other.store.close()


def _leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    else:
        yield value


if __name__ == "__main__":
    unittest.main()
