"""Consequential store operations re-check current membership authority."""
import unittest

from tideway.domain import ValidationError
from tideway.selftest import SHAPLA, TARGET, _mandate, _ops
from tideway.service import Tideway


class MembershipRevocationTests(unittest.TestCase):
    def test_removed_approver_cannot_leave_a_stale_approval(self):
        app = Tideway(":memory:")
        owner, accountant, _ = _ops(app)
        plan = app.propose(SHAPLA, TARGET, "agent:revocation")

        app.store.remove_member(SHAPLA, owner, accountant["id"])

        with self.assertRaisesRegex(ValidationError, "active membership"):
            app.store.approve(SHAPLA, plan["plan_id"], "recommended", accountant, "1357", "operator:imran")

        with app.store.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM approvals WHERE plan_id=?", (plan["plan_id"],)).fetchone())

    def test_removed_approver_cannot_execute_or_cancel_a_live_mandate(self):
        app = Tideway(":memory:")
        owner, accountant, _ = _ops(app)
        _, mandate = _mandate(app, SHAPLA)
        app.negotiate(SHAPLA, mandate["mandate_id"], "agent:revocation")
        app.store.remove_member(SHAPLA, owner, accountant["id"])

        with self.assertRaisesRegex(ValidationError, "active membership"):
            app.store.execute(SHAPLA, mandate["mandate_id"], "revoked-execute", accountant, "operator:imran")
        with self.assertRaisesRegex(ValidationError, "active membership"):
            app.store.cancel_mandate(SHAPLA, mandate["mandate_id"], accountant, "operator:imran")


if __name__ == "__main__":
    unittest.main()
