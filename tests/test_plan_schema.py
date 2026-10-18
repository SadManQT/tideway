"""Generation grammar is opt-in assistance, never the financial authority."""
import copy
import json
import unittest
from unittest.mock import patch

from tideway import copilot
from tideway.domain import SecurityError, ValidationError
from tideway.local_model import LocalModel, LocalModelUnavailable
from tideway.plan_schema import PLAN_SCHEMA, plan_schema
from tideway.service import Tideway


def branches(schema):
    return {branch["properties"]["tool"]["const"]: branch
            for branch in schema["properties"]["calls"]["items"]["anyOf"]}


class PlanSchemaContract(unittest.TestCase):
    def test_tool_union_and_argument_keys_match_authoritative_allowlist(self):
        union = branches(PLAN_SCHEMA)
        self.assertEqual(set(union), set(copilot.TOOLS))
        self.assertFalse(PLAN_SCHEMA["additionalProperties"])
        self.assertEqual(PLAN_SCHEMA["properties"]["calls"]["maxItems"], copilot.MAX_CALLS)
        for tool, allowed in copilot.TOOLS.items():
            with self.subTest(tool=tool):
                branch = union[tool]
                self.assertFalse(branch["additionalProperties"])
                args = branch["properties"]["args"]
                self.assertFalse(args["additionalProperties"])
                self.assertEqual(set(args["properties"]), allowed)
                self.assertLessEqual(set(args["required"]), allowed)
        self.assertFalse({"approve", "execute", "transfer", "sql", "shell"} & set(union))

    def test_risk_tools_require_empty_args_and_delays_are_name_to_integer_map(self):
        union = branches(PLAN_SCHEMA)
        for tool in ("simulate_risk", "counterparty_risk", "security_check", "explain_plan", "bank_pack"):
            self.assertEqual(union[tool]["properties"]["args"],
                             {"type": "object", "properties": {}, "required": [], "additionalProperties": False})
        delay = union["what_if"]["properties"]["args"]["properties"]["customer_delays"]["anyOf"][0]
        self.assertEqual(delay["additionalProperties"], {"type": "integer", "minimum": -30, "maximum": 90})
        self.assertEqual(delay["maxProperties"], copilot.MAX_NAMES)

    def test_scoped_customer_names_are_exact_and_cannot_mutate_global_schema(self):
        before = copy.deepcopy(PLAN_SCHEMA)
        scoped = plan_schema(["Bay Logistics", "Nila Traders", "Bay Logistics"])
        union = branches(scoped)
        delays = union["what_if"]["properties"]["args"]["properties"]["customer_delays"]["anyOf"][0]
        self.assertEqual(set(delays["properties"]), {"Bay Logistics", "Nila Traders"})
        self.assertFalse(delays["additionalProperties"])
        self.assertEqual(union["credit_check"]["properties"]["args"]["properties"]["customer"]["enum"],
                         ["Bay Logistics", "Nila Traders"])
        scoped["properties"]["intent"]["maxLength"] = 999
        self.assertEqual(PLAN_SCHEMA, before)
        self.assertEqual(plan_schema([]), PLAN_SCHEMA)
        with self.assertRaises(ValueError):
            plan_schema([""])

    def test_only_supported_optional_nulls_are_in_generation_schema(self):
        nullable = {"what_if": ("customer_delays", "extra_expense", "drop_invoice_customer"),
                    "propose_plan": ("exclude_counterparties", "max_discount_pct", "prefer"),
                    "draft_reminders": ("customers",), "customer_report": ("customer",)}
        for schema in (PLAN_SCHEMA, plan_schema(["Bay Logistics"])):
            union = branches(schema)
            for tool, fields in nullable.items():
                for field in fields:
                    with self.subTest(tool=tool, field=field):
                        copilot.validate_plan({"calls": [{"tool": tool, "args": {field: None}}]})
                        self.assertIn({"type": "null"}, union[tool]["properties"]["args"]["properties"][field]["anyOf"])
            for tool, field in (("project_cash", "scenario"), ("refuse", "reason"),
                                ("credit_check", "customer"), ("credit_check", "amount"),
                                ("credit_check", "terms_days"), ("credit_check", "currency")):
                with self.subTest(tool=tool, field=field):
                    self.assertNotIn("anyOf", union[tool]["properties"]["args"]["properties"][field])
                    args = {"customer": "Bay Logistics", "amount": 100, "terms_days": 30} if tool == "credit_check" else {}
                    args[field] = None
                    with self.assertRaises(ValidationError):
                        copilot.validate_plan({"calls": [{"tool": tool, "args": args}]})
        date = branches(PLAN_SCHEMA)["what_if"]["properties"]["args"]["properties"]["extra_expense"]["anyOf"][0]["properties"]["date"]
        self.assertEqual(date["pattern"], "^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

    def test_valid_examples_still_pass_authority_and_malformed_args_do_not(self):
        examples = {
            "project_cash": {"scenario": "likely"}, "simulate_risk": {},
            "reverse_stress": {}, "agreement_stress": {}, "recovery_options": {},
            "what_if": {"customer_delays": {"Bay Logistics": 7},
                        "extra_expense": {"amount": 100, "date": "2026-10-20", "currency": "BDT"}},
            "propose_plan": {"exclude_counterparties": [], "max_discount_pct": 2.5, "prefer": "lowest_cost"},
            "explain_plan": {}, "credit_check": {"customer": "Nila Traders", "amount": 50000, "terms_days": 30},
            "draft_reminders": {"customers": ["Nila Traders"]}, "bank_pack": {},
            "customer_report": {"customer": "Bay Logistics"}, "counterparty_risk": {}, "security_check": {},
            "refuse": {"reason": "approve_or_move_money"},
        }
        self.assertEqual(set(examples), set(copilot.TOOLS))
        for tool, args in examples.items():
            with self.subTest(tool=tool):
                copilot.validate_plan({"intent": "test", "calls": [{"tool": tool, "args": args}]})
        for tool, args in (("simulate_risk", {"customer": "Nila Traders"}),
                           ("what_if", {"customer_delays": {"name": "Nila Traders", "days": 7}}),
                           ("credit_check", {"customer": "Nila Traders", "amount": True, "terms_days": 30})):
            with self.subTest(tool=tool), self.assertRaises(ValidationError):
                copilot.validate_plan({"calls": [{"tool": tool, "args": args}]})

    def test_schema_is_not_permission_even_if_server_ignores_it(self):
        app = Tideway(":memory:")
        self.addCleanup(app.store.close)
        before = app.store.snapshot("shapla-services")["snapshot_hash"]
        for plan, role in (({"calls": [{"tool": "execute", "args": {}}]}, "owner"),
                           ({"calls": [{"tool": "propose_plan", "args": {}}]}, "viewer"),
                           ({"calls": [{"tool": "what_if", "args": {"customer_delays": {"Invented Name": 7}}}]}, "owner")):
            with self.subTest(plan=plan), self.assertRaises((SecurityError, ValidationError)):
                copilot.preflight_plan(app, "shapla-services", None, plan, role)
        self.assertEqual(before, app.store.snapshot("shapla-services")["snapshot_hash"])


class StructuredLocalTransport(unittest.TestCase):
    def test_default_transport_remains_json_object_and_schema_requires_opt_in(self):
        response = {"choices": [{"message": {"content": '{"calls":[]}'}}]}
        model = LocalModel("http://127.0.0.1:8790/v1", "test-local")
        with patch.object(model, "_request", return_value=response) as request:
            model.generate("system", "question")
            self.assertEqual(request.call_args.args[2]["response_format"], {"type": "json_object"})
            model.generate("system", "question", response_schema=PLAN_SCHEMA)
            payload = request.call_args.args[2]
            self.assertEqual(payload["response_format"], {"type": "json_schema", "json_schema": {
                "name": "tideway_plan", "strict": True, "schema": PLAN_SCHEMA}})
            self.assertEqual(payload["messages"][1]["content"], "question")
            json.dumps(payload, allow_nan=False)

    def test_unsupported_schema_fails_without_loose_retry(self):
        model = LocalModel("http://127.0.0.1:8790/v1", "test-local")
        with patch.object(model, "_request", side_effect=LocalModelUnavailable("HTTP 400")) as request:
            with self.assertRaisesRegex(LocalModelUnavailable, "HTTP 400"):
                model.generate("system", "question", response_schema=PLAN_SCHEMA)
            self.assertEqual(request.call_count, 1)
        with patch.object(model, "_request") as request:
            with self.assertRaisesRegex(LocalModelUnavailable, "JSON Schema object"):
                model.generate("system", "question", response_schema="not a schema")
            request.assert_not_called()
