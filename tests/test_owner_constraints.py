"""Owner instructions remain binding across negotiation, approval and replanning."""
import copy
import unittest

from tideway.domain import ValidationError, canonical_json
from tideway.service import Tideway
from tideway.store import json_hash


BUSINESS = "shapla-services"


class OwnerConstraints(unittest.TestCase):
    def setUp(self):
        self.app = Tideway(":memory:")
        self.addCleanup(self.app.store.close)
        self.owner = self.app.store.verify_pin("nadia", "2468")

    def propose(self, cap=100, prefer="lowest_risk"):
        return self.app.propose(BUSINESS, None, "agent:test", max_discount_bps=cap,
                                prefer=prefer, excluded=("Rahman Supplies",))

    def approve(self, plan):
        bundle = plan["bundles"][0]
        terms = self.app.store.risk_acknowledgement_terms(plan, bundle)
        acknowledgement = {"acknowledged": True, **terms} if terms else None
        for identifier, pin in (("imran", "1357"), ("nadia", "2468")):
            who = self.app.store.verify_pin(identifier, pin)
            result = self.app.store.approve(BUSINESS, plan["plan_id"], bundle["bundle_id"], who,
                                           pin, "operator:" + identifier,
                                           risk_acknowledgement=acknowledgement)
            if result["status"] == "mandate_issued":
                return result["mandate"]
        self.fail("No mandate issued")

    def negotiated(self, cap=100, prefer="lowest_risk"):
        plan = self.propose(cap, prefer)
        mandate = self.approve(plan)
        view = self.app.negotiate(BUSINESS, mandate["mandate_id"], "agent:test")
        self.assertEqual(view["status"], "countered")
        return plan, mandate

    def counts(self):
        with self.app.store.connect() as db:
            return tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                         for table in ("plans", "mandates", "approvals", "audit"))

    def rewrite(self, plan, mutate):
        """Simulate a faulty internal producer, including its recomputed plan hash."""
        with self.app.store.connect() as db:
            import json
            payload = json.loads(db.execute("SELECT payload FROM plans WHERE id=?", (plan["plan_id"],)).fetchone()[0])
            mutate(payload)
            db.execute("UPDATE plans SET payload=?,plan_hash=? WHERE id=?",
                       (canonical_json(payload), json_hash(payload), plan["plan_id"]))

    def test_above_owner_cap_counter_is_rejected_without_consuming_mandate(self):
        _, mandate = self.negotiated()
        before = self.counts()
        with self.assertRaisesRegex(ValidationError, "discount|ceiling"):
            self.app.accept_counter(BUSINESS, mandate["mandate_id"], "agent:test")
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.app.store.mandate(BUSINESS, mandate["mandate_id"])["status"], "countered")

    def test_replan_preserves_cap_preference_exclusions_and_provenance(self):
        for prefer in ("lowest_cost", "lowest_risk", "fewest_asks"):
            with self.subTest(prefer=prefer):
                plan, mandate = self.negotiated(prefer=prefer)
                fresh = self.app.replan_without(BUSINESS, mandate["mandate_id"], "agent:test")
                self.assertEqual(fresh["owner_constraints"], {"max_discount_bps": 100, "prefer": prefer})
                self.assertTrue(set(plan["excluded_counterparties"]) <= set(fresh["excluded_counterparties"]))
                self.assertIn("Bay Logistics", fresh["excluded_counterparties"])
                self.assertEqual(fresh["target_date"], plan["target_date"])
                self.assertEqual(fresh["supersedes"]["plan_id"], plan["plan_id"])
                self.assertFalse(fresh["approvals"])
                with self.assertRaises(ValidationError):
                    self.app.store.execute(BUSINESS, mandate["mandate_id"], "old", self.owner, "operator:nadia")

    def test_exact_owner_ceiling_counter_still_needs_fresh_approval(self):
        plan, mandate = self.negotiated(cap=150)
        fresh = self.app.accept_counter(BUSINESS, mandate["mandate_id"], "agent:test")
        self.assertFalse(fresh["approvals"])
        self.assertEqual(fresh["owner_constraints"], plan["owner_constraints"])
        discounts = [a["discount_bps"] for b in fresh["bundles"] for a in b["actions"] if a["type"] == "early_payment_offer"]
        self.assertIn(150, discounts)
        self.assertTrue(all(bps <= 150 for bps in discounts))
        approved = self.approve(fresh)
        self.assertEqual(approved["owner_constraints"], plan["owner_constraints"])
        self.assertEqual(self.app.negotiate(BUSINESS, approved["mandate_id"], "agent:test")["status"], "ready")
        receipt = self.app.store.execute(BUSINESS, approved["mandate_id"], "fresh-constraints", self.owner, "operator:nadia")
        self.assertEqual(receipt["owner_constraints"], plan["owner_constraints"])
        self.assertTrue(receipt["read_back"]["verified"])

    def test_store_rejects_a_replacement_that_widens_the_owner_cap(self):
        plan, mandate = self.negotiated()
        payload = copy.deepcopy(plan)
        payload["owner_constraints"]["max_discount_bps"] = 300
        before = self.counts()
        with self.assertRaisesRegex(ValidationError, "constraint|ceiling|discount"):
            self.app.store.create_plan(BUSINESS, payload, plan["snapshot_hash"], "agent:test", "agent:test",
                                       replaces_mandate=mandate["mandate_id"])
        self.assertEqual(before, self.counts())

    def test_store_rejects_a_replacement_that_changes_preference_or_drops_exclusions(self):
        plan, mandate = self.negotiated()
        for key in ("preference", "exclusions"):
            before = self.counts()
            payload = copy.deepcopy(plan)
            if key == "preference":
                payload["owner_constraints"]["prefer"] = "fewest_asks"
            else:
                payload["excluded_counterparties"] = []
            with self.subTest(key=key), self.assertRaises(ValidationError):
                self.app.store.create_plan(BUSINESS, payload, plan["snapshot_hash"], "agent:test", "agent:test",
                                           replaces_mandate=mandate["mandate_id"])
            self.assertEqual(self.counts(), before)
            self.assertEqual(self.app.store.mandate(BUSINESS, mandate["mandate_id"])["status"], "countered")

    def test_approval_rejects_faulty_producer_discount_above_stored_owner_cap(self):
        plan = self.propose(cap=300)
        self.rewrite(plan, lambda body: body.update(owner_constraints={"max_discount_bps": 0, "prefer": "lowest_risk"}))
        with self.assertRaisesRegex(ValidationError, "discount|ceiling"):
            self.approve(self.app.store.plan(BUSINESS, plan["plan_id"]))

    def test_execution_rechecks_owner_ceiling_on_legacy_signed_terms(self):
        plan, mandate = self.negotiated()
        # Give a legacy faulty plan a cap below its already-signed offer.
        self.rewrite(plan, lambda body: body["owner_constraints"].update(max_discount_bps=0))
        fresh = self.app.store.plan(BUSINESS, plan["plan_id"])
        from tideway import security
        mandate["plan_hash"] = fresh["plan_hash"]
        mandate["signature"] = security.sign(self.app.store.key, mandate)
        with self.app.store.connect() as db:
            db.execute("UPDATE mandates SET document=? WHERE id=?", (canonical_json(mandate), mandate["mandate_id"]))
        before = self.app.store.snapshot(BUSINESS)["state"]["state_hash"]
        with self.assertRaisesRegex(ValidationError, "discount|ceiling|constraint"):
            self.app.store.execute(BUSINESS, mandate["mandate_id"], "faulty", self.owner, "operator:nadia")
        self.assertEqual(before, self.app.store.snapshot(BUSINESS)["state"]["state_hash"])

    def test_legacy_plan_without_recorded_constraints_requires_new_owner_proposal(self):
        plan, mandate = self.negotiated()
        self.rewrite(plan, lambda body: body.pop("owner_constraints"))
        before = self.counts()
        with self.assertRaisesRegex(ValidationError, "constraint|fresh|owner"):
            self.app.replan_without(BUSINESS, mandate["mandate_id"], "agent:test")
        self.assertEqual(before, self.counts())

    def test_invalid_direct_owner_arguments_are_rejected(self):
        for cap in (True, -1, 1.5, "100", 1001):
            with self.subTest(cap=cap), self.assertRaises(ValidationError):
                self.propose(cap=cap)
        with self.assertRaises(ValidationError):
            self.propose(prefer="invented")

    def test_zero_stricter_and_more_permissive_policy_do_not_widen_owner_ceiling(self):
        from tideway.constraints import owner_constraints
        for owner_cap, policy_cap, expected in ((0, 300, 0), (100, 50, 50), (100, 300, 100)):
            with self.subTest(owner=owner_cap, policy=policy_cap):
                self.assertEqual(owner_constraints({"max_discount_bps": owner_cap, "prefer": "fewest_asks"},
                                                   {"max_discount_bps": policy_cap}),
                                 {"max_discount_bps": expected, "prefer": "fewest_asks"})


class RiskDisplayBoundaries(unittest.TestCase):
    def test_exact_risk_target_and_rounding_do_not_supply_implicit_consent(self):
        from tideway.store import Store
        plan = {"plan_id": "p", "plan_hash": "h", "risk_target": .10}
        self.assertIsNone(Store.risk_acknowledgement_terms(plan, {"bundle_id": "b", "probability_breach_after": .10}))
        for probability in (.10000001, .1049, .1178):
            terms = Store.risk_acknowledgement_terms(plan, {"bundle_id": "b", "probability_breach_after": probability})
            self.assertEqual(terms["probability_breach_after"], probability)
            with self.assertRaises(ValidationError):
                Store._validate_risk_acknowledgement(terms, None)
