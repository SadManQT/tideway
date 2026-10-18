"""Focused regressions for counterparty-network projection scenarios."""
import unittest

from tideway.selftest import SHAPLA, TARGET, _mandate, _ops
from tideway.service import Tideway


class CounterpartyNetworkRegression(unittest.TestCase):
    def test_baseline_network_keeps_never_pays_impact(self):
        app = Tideway(":memory:")

        network = app.network(SHAPLA, TARGET)
        nila = next(item for item in network["customers"] if item["name"] == "Nila Traders")

        self.assertEqual(nila["if_never_pays"]["horizon_cash_drop_minor"], nila["open_minor"])
        impacts = [item["expected_impact_minor"] for item in network["customers"]]
        self.assertEqual(impacts, sorted(impacts, reverse=True))

    def test_network_after_executed_early_payment_keeps_stress_valid(self):
        app = Tideway(":memory:")
        plan, mandate = _mandate(app, SHAPLA)
        bundle = next(item for item in plan["bundles"] if item["bundle_id"] == mandate["bundle_id"])
        early_payment = next(item for item in bundle["actions"] if item["type"] == "early_payment_offer")

        negotiation = app.negotiate(SHAPLA, mandate["mandate_id"], "agent:network-regression")
        self.assertEqual(negotiation["status"], "ready")
        owner, _, _ = _ops(app)
        receipt = app.store.execute(SHAPLA, mandate["mandate_id"], "network-regression", owner, "operator:nadia")
        self.assertEqual(receipt["status"], "executed")

        before_network = app.store.snapshot(SHAPLA)["state"]
        network = app.network(SHAPLA, TARGET)
        after_network = app.store.snapshot(SHAPLA)["state"]

        nila = next(item for item in network["customers"] if item["name"] == "Nila Traders")
        self.assertEqual(nila["if_never_pays"]["horizon_cash_drop_minor"], early_payment["adjustment"]["amount_minor"])
        self.assertEqual(nila["impact_if_never_pays_minor"], early_payment["adjustment"]["amount_minor"])
        self.assertEqual(after_network, before_network)


if __name__ == "__main__":
    unittest.main()
