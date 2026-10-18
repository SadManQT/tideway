"""Atomic owner-authorised synthetic events and durable replan coordination."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone

from .constraints import check_plan_constraints
from .domain import OPEN_INVOICE_STATUSES, ValidationError, canonical_json, valid_date, validate_transaction, MAX_AMOUNT_MINOR, add_days


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hashed(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class EventStoreMixin:
    def _event_owner(self, db, business_id, operator):
        role = db.execute("SELECT role FROM memberships WHERE business_id=? AND operator_id=?", (business_id, operator["id"])).fetchone()
        if not role or role["role"] != "owner":
            raise ValidationError("An owner membership is required for synthetic events.")
        snapshot = self._snapshot(db, business_id)
        if not snapshot["business"]["synthetic"]:
            raise ValidationError("Event injection is restricted to synthetic businesses.")
        if snapshot["policy"]["agent_paused"]:
            raise ValidationError("Resume the paused agent before processing synthetic events.")
        return snapshot

    def event_watch(self, business_id):
        with self.connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key=?", ("event-watch:" + business_id,)).fetchone()
            prefix = "lab-event:" + business_id + ":"
            events = [json.loads(r[0])["receipt"] for r in db.execute("SELECT value FROM metadata WHERE substr(key,1,?)=? ORDER BY rowid DESC LIMIT 20", (len(prefix), prefix))]
        return {"enabled": bool(row and json.loads(row[0])["enabled"]), "events": events}

    def set_event_watch(self, business_id, enabled, operator, pin, actor):
        if type(enabled) is not bool:
            raise ValidationError("enabled must be true or false.")
        self.verify_pin(operator["id"], pin)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._event_owner(db, business_id, operator)
            value = {"enabled": enabled, "authorised_by": operator["id"], "updated_at": stamp()}
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?)", ("event-watch:" + business_id, canonical_json(value)))
            return {**value, **self._audit(db, business_id, "events.watch", actor, "human_approval", value)}

    def apply_lab_event(self, business_id, event, target, expected_snapshot, request_id, operator, pin, actor):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id):
            raise ValidationError("Use a request id of 8-80 safe characters.")
        if not isinstance(expected_snapshot, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_snapshot):
            raise ValidationError("A current snapshot hash is required.")
        schemas = {"invoice_delay": {"type", "record_id", "date"}, "invoice_received": {"type", "record_id", "date"},
                   "unexpected_expense": {"type", "amount_minor", "date"}, "supplier_refused": {"type", "record_id"}}
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or event["type"] not in schemas or set(event) != schemas[event["type"]]:
            raise ValidationError("Select a supported event and its exact fields.")
        if "record_id" in event and (not isinstance(event["record_id"], str) or len(event["record_id"]) > 100):
            raise ValidationError("Invalid record id.")
        if "date" in event:
            valid_date(event["date"], "Event date")
        if "amount_minor" in event and (type(event["amount_minor"]) is not int or not 0 < event["amount_minor"] <= MAX_AMOUNT_MINOR):
            raise ValidationError("Expense amount must be a positive bounded integer.")
        self.verify_pin(operator["id"], pin)
        signature = hashed({"event": event, "target": target, "snapshot": expected_snapshot, "operator": operator["id"]})
        key = f"lab-event:{business_id}:{request_id}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            snapshot = self._event_owner(db, business_id, operator)
            saved = db.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
            if saved:
                value = json.loads(saved[0])
                if value["signature"] != signature:
                    raise ValidationError("Request id already used for different event terms.")
                return {**value["receipt"], "replayed": True}
            if snapshot["snapshot_hash"] != expected_snapshot:
                raise ValidationError("Records changed. Refresh before applying the event.")
            from .resilience import Context
            from .projection import summary
            before_projection = summary(Context(snapshot, target).projection())
            state, business = snapshot["state"], snapshot["business"]
            from .projection import horizon_end
            end = horizon_end(business, target, snapshot["policy"]["lookahead_days"])
            if "date" in event and not state["current_date"] <= event["date"] <= end:
                raise ValidationError("Event date must lie between the simulation date and the planning horizon.")
            previous = db.execute("SELECT id,payload,plan_hash FROM plans WHERE business_id=? AND target_date=? AND snapshot_hash=? AND status IN ('pending','approved') ORDER BY created_at DESC,rowid DESC LIMIT 1",
                                  (business_id, target, expected_snapshot)).fetchone()
            payload = json.loads(previous["payload"]) if previous else None
            inherited = None
            if payload is None:
                prefix = "lab-event:" + business_id + ":"
                # Repeated events may arrive before a replacement proposal is saved.
                # Only inherit instructions from this exact prior ledger state.
                for row in db.execute("SELECT value FROM metadata WHERE substr(key,1,?)=? ORDER BY rowid DESC LIMIT 20", (len(prefix), prefix)):
                    candidate = json.loads(row[0])["receipt"]
                    if candidate["after_snapshot"] == expected_snapshot and candidate["target_date"] == target:
                        inherited = candidate
                        break
            constraints = check_plan_constraints(payload, snapshot["policy"]) if payload else {
                "max_discount_bps": snapshot["policy"]["max_discount_bps"], "prefer": "lowest_cost"}
            if inherited:
                constraints = inherited["owner_constraints"]
            excluded = list((payload or inherited or {}).get("excluded_counterparties", []))
            pact = next((b["bilateral"] for b in (payload or {}).get("bundles", []) if b.get("bilateral")), None)
            if inherited:
                pact = inherited.get("bilateral")
            invalidated = [r[0] for r in db.execute("SELECT id FROM mandates WHERE business_id=? AND kind='bundle' AND status IN ('active','ready','countered','rejected')", (business_id,))]
            transaction = None
            if event["type"] in ("invoice_delay", "invoice_received"):
                invoice = next((r for r in snapshot["records"]["invoices"] if r["id"] == event["record_id"]), None)
                if not invoice or invoice["status"] not in OPEN_INVOICE_STATUSES or invoice["risk_flags"]:
                    raise ValidationError("Select an open, unquarantined invoice.")
                if event["date"] < invoice["issue_date"]:
                    raise ValidationError("An invoice cannot be received before it was issued.")
                if event["type"] == "invoice_delay":
                    if event["date"] <= max(invoice["expected_collection_date"], state["promises"].get(invoice["id"], "")):
                        raise ValidationError("Choose a later collection date than the existing expected or promised date.")
                    if any(a.get("invoice_id") == invoice["id"] for a in state["adjustments"]):
                        raise ValidationError("This invoice has executed terms; use an unadjusted invoice for delay injection.")
                    db.execute("UPDATE invoices SET expected_collection_date=? WHERE business_id=? AND id=?", (event["date"], business_id, invoice["id"]))
                else:
                    amount = next((a["amount_minor"] for a in state["adjustments"] if a.get("invoice_id") == invoice["id"]), invoice["amount_minor"])
                    transaction = {"type": "income", "category": "Customer receipt", "amount_minor": amount}
                    db.execute("UPDATE invoices SET status='collected',paid_date=? WHERE business_id=? AND id=?", (event["date"], business_id, invoice["id"]))
                    state["adjustments"] = [a for a in state["adjustments"] if a.get("invoice_id") != invoice["id"]]
                    db.execute("UPDATE sandbox_state SET current_date=? WHERE business_id=?", (event["date"], business_id))
                state["promises"].pop(invoice["id"], None)
            elif event["type"] == "unexpected_expense":
                transaction = {"type": "expense", "category": "Unexpected expense", "amount_minor": event["amount_minor"]}
            else:
                bill = next((r for r in snapshot["records"]["bills"] if r["id"] == event["record_id"]), None)
                if not bill or bill["status"] not in ("open", "scheduled") or bill["risk_flags"]:
                    raise ValidationError("Select an open, unquarantined supplier bill.")
                if any(a.get("bill_id") == bill["id"] for a in state["adjustments"]):
                    raise ValidationError("This bill already has executed terms.")
                excluded = sorted(set(excluded + [bill["payee"]]))
                db.execute("UPDATE bills SET reschedule_allowed=0 WHERE business_id=? AND id=?", (business_id, bill["id"]))
            if transaction:
                row = validate_transaction({"id": "evt-" + request_id, "date": event["date"], "description": "Synthetic event " + event["type"],
                                            "currency": business["currency"], **transaction}, business_id, business["currency"])
                db.execute("INSERT INTO transactions(business_id,id,date,description,type,amount_minor,currency,category,fingerprint,risk_flags,source,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                           (business_id, row["id"], row["date"], row["description"], row["type"], row["amount_minor"], business["currency"], row["category"], hashed(row), "[]", "lab-event", stamp()))
            db.execute("UPDATE sandbox_state SET state_json=? WHERE business_id=?", (canonical_json({k: state[k] for k in ("adjustments", "promises", "executed_exposure")}), business_id))
            version = self._bump(db, business_id)
            after = self._snapshot(db, business_id)
            watch = db.execute("SELECT value FROM metadata WHERE key=?", ("event-watch:" + business_id,)).fetchone()
            receipt = {"request_id": request_id, "event": event, "target_date": target, "before_snapshot": expected_snapshot,
                       "after_snapshot": after["snapshot_hash"], "state_version": version, "owner_constraints": constraints,
                       "before_projection": before_projection, "after_projection": summary(Context(after, target).projection()),
                       "excluded_counterparties": excluded, "invalidated_mandates": invalidated, "plan_id": None,
                       "watch_enabled": bool(watch and json.loads(watch[0])["enabled"]), "replayed": False,
                       "previous_plan_id": previous["id"] if previous else (inherited or {}).get("previous_plan_id"),
                       "bilateral": pact, "created_at": stamp()}
            receipt.update(self._audit(db, business_id, "events.applied", actor, "human_approval", receipt))
            db.execute("INSERT INTO metadata(key,value) VALUES (?,?)", (key, canonical_json({"signature": signature, "receipt": receipt})))
            return receipt
