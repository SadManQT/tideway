"""Validated records and deterministic cash-flow calculations.

The original FinMate prototype contained a personal budgeting model.  Those
helpers are still available at the bottom of this module for the old demo,
but Probaho uses the business-scoped records and integer minor-unit
calculations in the first half of the file.

All monetary values ending in ``_minor`` are integer BDT paisa.  A value in a
human-facing request (``amount`` or ``reserve_floor``) is parsed as BDT and
converted exactly once at the boundary.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


class ValidationError(ValueError):
    """A user-correctable input or policy validation error."""


PROBAHO_CURRENCY = "BDT"
MAX_AMOUNT_MINOR = 100_000_000 * 100
MAX_PROJECTION_DAYS = 366
BUSINESS_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
SCENARIOS = ("base", "late_collection", "approved_recovery")
TRANSACTION_TYPES = ("income", "expense")
INVOICE_STATUSES = ("draft", "confirmed", "paid", "collected", "overdue", "cancelled", "disputed")
BILL_STATUSES = ("open", "scheduled", "paid", "cancelled", "rescheduled")
BILL_PRIORITIES = ("payroll", "critical", "high", "normal", "low")


def valid_date(value, field="Date") -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ValidationError(f"{field} must use YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} is not valid.") from None
    return value


def validate_business_id(value) -> str:
    if not isinstance(value, str) or not BUSINESS_ID_RE.fullmatch(value):
        raise ValidationError("business_id must contain 1-64 letters, numbers, '_' or '-'.")
    return value


def normalize_currency(value, required=False) -> str:
    if value is None or value == "":
        if required:
            raise ValidationError("Currency is required.")
        return PROBAHO_CURRENCY
    if not isinstance(value, str) or value.strip().upper() != PROBAHO_CURRENCY:
        raise ValidationError("This prototype supports BDT only; mixed currencies are not accepted.")
    return PROBAHO_CURRENCY


def money_minor(value) -> int:
    """Parse a strictly positive BDT amount expressed in BDT units."""
    if isinstance(value, bool):
        raise ValidationError("Amount must be a positive monetary value.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValidationError("Amount must be a number.") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("100000000"):
        raise ValidationError("Amount must be greater than zero and at most 100,000,000 BDT.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError("Amount may have at most two decimal places.")
    return int(amount * 100)


def nonnegative_minor(value, field="Amount", maximum=MAX_AMOUNT_MINOR) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer minor-unit amount.")
    if value < 0 or value > maximum:
        raise ValidationError(f"{field} must be a non-negative integer minor-unit amount.")
    return value


def record_amount_minor(raw: dict, field="Amount") -> int:
    """Read either an exact ``*_minor`` value or a BDT decimal amount.

    Supplying both forms is allowed only when they agree.  This makes import
    and API retries deterministic and prevents a float conversion from
    silently changing the value.
    """
    if not isinstance(raw, dict):
        raise ValidationError(f"{field} must be an object field.")
    minor_key = "amount_minor"
    has_minor = minor_key in raw and raw.get(minor_key) not in (None, "")
    has_amount = "amount" in raw and raw.get("amount") not in (None, "")
    if not has_minor and not has_amount:
        raise ValidationError(f"{field} is required.")
    parsed_minor = None
    if has_minor:
        value = raw.get(minor_key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError("amount_minor must be an integer.")
        if value <= 0 or value > MAX_AMOUNT_MINOR:
            raise ValidationError("amount_minor must be greater than zero and within the supported limit.")
        parsed_minor = value
    if has_amount:
        parsed_amount = money_minor(raw.get("amount"))
        if parsed_minor is not None and parsed_minor != parsed_amount:
            raise ValidationError("amount and amount_minor do not agree.")
        parsed_minor = parsed_amount
    return parsed_minor


def _text(raw, key, required=True, limit=300, label=None):
    value = raw.get(key, "")
    if not isinstance(value, str):
        raise ValidationError(f"{label or key} must be text.")
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{label or key} is required.")
    if len(value) > limit or any(ord(c) < 32 and c not in "\t" for c in value):
        raise ValidationError(f"{label or key} must contain printable text of at most {limit} characters.")
    return value


def _bool(raw, key, default=False):
    value = raw.get(key, default)
    if isinstance(value, str) and not value.strip():
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes", "y"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no", "n"):
        return False
    raise ValidationError(f"{key} must be true or false.")


def _flag(value, field="flag"):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes", "y"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no", "n", ""):
        return False
    raise ValidationError(f"{field} must be true or false.")


def _date_or_default(raw, key, fallback_key=None):
    value = raw.get(key)
    if value in (None, "") and fallback_key:
        value = raw.get(fallback_key)
    return valid_date(value, key)


def validate_business(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Business must be an object.")
    identifier = validate_business_id(raw.get("business_id", raw.get("id", "")))
    name = _text(raw, "name", limit=120)
    currency = normalize_currency(raw.get("currency", PROBAHO_CURRENCY), required=True)
    opening = raw.get("opening_cash_minor")
    if opening is None:
        opening_value = raw.get("opening_cash", raw.get("opening_balance"))
        if opening_value is None:
            raise ValidationError("opening_cash is required.")
        try:
            amount = Decimal(str(opening_value).strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ValidationError("opening_cash must be a non-negative monetary value.") from None
        if not amount.is_finite() or amount < 0 or amount > Decimal("100000000") or amount != amount.quantize(Decimal("0.01")):
            raise ValidationError("opening_cash must be a non-negative amount with at most two decimals.")
        opening = int(amount * 100)
    opening = nonnegative_minor(opening, "opening_cash_minor")
    opening_date = valid_date(raw.get("opening_date", "2026-10-01"), "opening_date")
    target_date = valid_date(raw.get("default_target_date", "2026-10-31"), "default_target_date")
    if target_date < opening_date:
        raise ValidationError("default_target_date cannot be before opening_date.")
    synthetic = raw.get("synthetic", True)
    if not isinstance(synthetic, bool):
        raise ValidationError("synthetic must be true or false.")
    return {"business_id": identifier, "name": name, "currency": currency,
            "opening_cash_minor": opening, "opening_date": opening_date,
            "default_target_date": target_date, "synthetic": synthetic}


def validate_policy(raw: dict, business_id=None) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Policy must be an object.")
    identifier = validate_business_id(business_id or raw.get("business_id", ""))
    if raw.get("business_id") not in (None, "", identifier):
        raise ValidationError("Policy business_id does not match the requested business.")
    currency = normalize_currency(raw.get("currency", PROBAHO_CURRENCY), required=True)
    reserve = raw.get("reserve_floor_minor")
    if reserve is None:
        try:
            amount = Decimal(str(raw.get("reserve_floor", "")).strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ValidationError("reserve_floor must be a non-negative monetary value.") from None
        if not amount.is_finite() or amount < 0 or amount > Decimal("100000000") or amount != amount.quantize(Decimal("0.01")):
            raise ValidationError("reserve_floor must be a non-negative amount with at most two decimals.")
        reserve = int(amount * 100)
    reserve = nonnegative_minor(reserve, "reserve_floor_minor")
    limit = raw.get("action_limit_minor")
    if limit is None:
        try:
            amount = Decimal(str(raw.get("action_limit", "")).strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ValidationError("action_limit must be a non-negative monetary value.") from None
        if not amount.is_finite() or amount < 0 or amount > Decimal("100000000") or amount != amount.quantize(Decimal("0.01")):
            raise ValidationError("action_limit must be a non-negative amount with at most two decimals.")
        limit = int(amount * 100)
    limit = nonnegative_minor(limit, "action_limit_minor")
    payroll_priority = raw.get("payroll_priority", True)
    if payroll_priority is not True:
        raise ValidationError("payroll_priority must be true for this protected payroll prototype.")
    version = raw.get("version", "probaho-policy-v1")
    if not isinstance(version, str) or not version or len(version) > 80:
        raise ValidationError("Policy version is invalid.")
    return {"business_id": identifier, "currency": currency,
            "reserve_floor_minor": reserve, "payroll_priority": payroll_priority,
            "action_limit_minor": limit, "version": version}


def validate_probaho_transaction(raw: dict, business_id=None) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Each transaction must be an object.")
    identifier = validate_business_id(business_id or raw.get("business_id", ""))
    if raw.get("business_id") not in (None, "", identifier):
        raise ValidationError("Record business_id does not match the requested business.")
    day = valid_date(raw.get("date", ""), "Transaction date")
    description = _text(raw, "description", limit=300)
    kind = raw.get("type", "")
    if not isinstance(kind, str) or kind.strip().lower() not in ("income", "expense"):
        raise ValidationError("Type must be income or expense.")
    kind = kind.strip().lower()
    currency = normalize_currency(raw.get("currency"), required=True)
    amount = record_amount_minor(raw)
    category = raw.get("category", "") or ("Income" if kind == "income" else "Other")
    category = _text({"category": category}, "category", limit=80)
    if kind == "income":
        category = "Income"
    record_id = raw.get("id") or raw.get("transaction_id")
    if record_id is not None and (not isinstance(record_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", record_id)):
        raise ValidationError("Transaction id must contain 1-80 safe characters.")
    return {"id": raw.get("id") or raw.get("transaction_id"), "business_id": identifier,
            "date": day, "description": description, "type": kind,
            "amount_minor": amount, "currency": currency, "category": category,
            "source": raw.get("source", "import")}


def validate_invoice(raw: dict, business_id=None) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Each invoice must be an object.")
    identifier = validate_business_id(business_id or raw.get("business_id", ""))
    if raw.get("business_id") not in (None, "", identifier):
        raise ValidationError("Record business_id does not match the requested business.")
    invoice_id = raw.get("id", raw.get("invoice_id"))
    if not isinstance(invoice_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", invoice_id):
        raise ValidationError("Invoice id must contain 1-80 safe characters.")
    amount = record_amount_minor(raw, "Invoice amount")
    currency = normalize_currency(raw.get("currency"), required=True)
    due_date = valid_date(raw.get("due_date", ""), "due_date")
    # The import contract only requires due_date; an omitted issue date is
    # conservatively treated as issued on the due date rather than accepted
    # as an ambiguous free-form date.
    issue_date = valid_date(raw.get("issue_date") or raw.get("date") or due_date, "issue_date")
    expected = valid_date(raw.get("expected_collection_date") or due_date, "expected_collection_date")
    if due_date < issue_date:
        raise ValidationError("Invoice due_date cannot be before issue_date.")
    if expected < issue_date:
        raise ValidationError("expected_collection_date cannot be before issue_date.")
    status = raw.get("status") or "confirmed"
    if not isinstance(status, str) or status.strip().lower() not in INVOICE_STATUSES:
        raise ValidationError("Invoice status is invalid.")
    status = status.strip().lower()
    customer = _text({"customer": raw.get("customer") or raw.get("counterparty") or "Customer"}, "customer", limit=160)
    description = _text({"description": raw.get("description") or "Receivable"}, "description", limit=300)
    return {"id": invoice_id, "business_id": identifier, "customer": customer,
            "description": description, "issue_date": issue_date, "due_date": due_date,
            "expected_collection_date": expected, "status": status,
            "amount_minor": amount, "currency": currency,
            "source": raw.get("source", "import")}


def validate_bill(raw: dict, business_id=None) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Each bill must be an object.")
    identifier = validate_business_id(business_id or raw.get("business_id", ""))
    if raw.get("business_id") not in (None, "", identifier):
        raise ValidationError("Record business_id does not match the requested business.")
    bill_id = raw.get("id", raw.get("bill_id"))
    if not isinstance(bill_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", bill_id):
        raise ValidationError("Bill id must contain 1-80 safe characters.")
    amount = record_amount_minor(raw, "Bill amount")
    currency = normalize_currency(raw.get("currency"), required=True)
    due_date = valid_date(raw.get("due_date", ""), "due_date")
    status = raw.get("status") or "open"
    if not isinstance(status, str) or status.strip().lower() not in BILL_STATUSES:
        raise ValidationError("Bill status is invalid.")
    status = status.strip().lower()
    payee = _text({"payee": raw.get("payee") or raw.get("counterparty") or "Supplier"}, "payee", limit=160)
    description = _text({"description": raw.get("description") or "Supplier bill"}, "description", limit=300)
    priority = raw.get("priority") or "normal"
    if not isinstance(priority, str) or priority.strip().lower() not in BILL_PRIORITIES:
        raise ValidationError("Bill priority is invalid.")
    priority = priority.strip().lower()
    reschedule_allowed = _bool(raw, "reschedule_allowed", False)
    rescheduled_date = raw.get("rescheduled_date")
    if rescheduled_date not in (None, ""):
        rescheduled_date = valid_date(rescheduled_date, "rescheduled_date")
        if rescheduled_date <= due_date:
            raise ValidationError("rescheduled_date must be later than due_date.")
    if status == "rescheduled" and not rescheduled_date:
        raise ValidationError("Rescheduled bills require rescheduled_date.")
    if status != "rescheduled" and rescheduled_date:
        raise ValidationError("rescheduled_date requires status=rescheduled.")
    return {"id": bill_id, "business_id": identifier, "payee": payee,
            "description": description, "due_date": due_date, "amount_minor": amount,
            "currency": currency, "status": status, "priority": priority,
            "reschedule_allowed": reschedule_allowed, "rescheduled_date": rescheduled_date,
            "source": raw.get("source", "import")}


def _row_business(raw, business_id):
    value = raw.get("business_id")
    if value not in (None, "", business_id):
        raise ValidationError("Every imported record must belong to the requested business.")
    return business_id


def parse_combined_csv(text: str, business_id: str, allow_legacy=True) -> dict:
    """Validate a transaction/invoice/bill CSV completely before persistence."""
    business_id = validate_business_id(business_id)
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1_500_000:
        raise ValidationError("CSV must be UTF-8 text and no larger than 1.5 MB.")
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        if not reader.fieldnames:
            raise ValidationError("CSV must contain a header row.")
        fields = [field.strip() if isinstance(field, str) else field for field in reader.fieldnames]
        if len(set(fields)) != len(fields):
            raise ValidationError("Duplicate CSV column names are not allowed.")
        reader.fieldnames = fields
        if "record_type" not in fields:
            # Legacy transaction-only CSV remains accepted through the old parser.
            if not allow_legacy:
                raise ValidationError("Combined Probaho CSV requires a record_type column.")
            return {"transactions": [validate_probaho_transaction({**row, "business_id": business_id}, business_id)
                                      for row in parse_csv(text)], "invoices": [], "bills": [], "legacy": True}
        rows = {"transactions": [], "invoices": [], "bills": []}
        seen = set()
        for line, raw in enumerate(reader, 2):
            if line > 5001:
                raise ValidationError("Import at most 5,000 rows at a time.")
            if None in raw:
                raise ValidationError(f"Row {line}: too many columns.")
            kind = str(raw.get("record_type", "")).strip().lower()
            if kind not in ("transaction", "invoice", "bill"):
                raise ValidationError(f"Row {line}: record_type must be transaction, invoice or bill.")
            raw["business_id"] = _row_business(raw, business_id)
            # CSV has no native integer type.  Accept only a canonical base-10
            # spelling for the exact minor-unit column; JSON/API callers still
            # have to provide an actual integer.
            if raw.get("amount_minor", "") not in (None, ""):
                value = raw.get("amount_minor")
                if isinstance(value, str) and re.fullmatch(r"\d+", value.strip()):
                    raw["amount_minor"] = int(value.strip())
                elif not isinstance(value, int):
                    raise ValidationError(f"Row {line}: amount_minor must be a non-negative integer.")
            # A new combined file must make the currency explicit.  This also
            # gives a clear error for the roadmap's missing-currency case.
            if not raw.get("currency", "").strip():
                raise ValidationError(f"Row {line}: currency is required.")
            try:
                if kind == "transaction":
                    normalized = validate_probaho_transaction(raw, business_id)
                    identity = (kind, normalized["id"] or normalized["date"] + "|" + normalized["description"] + "|" + str(normalized["amount_minor"]))
                    rows["transactions"].append(normalized)
                elif kind == "invoice":
                    normalized = validate_invoice(raw, business_id)
                    identity = (kind, normalized["id"])
                    rows["invoices"].append(normalized)
                else:
                    normalized = validate_bill(raw, business_id)
                    identity = (kind, normalized["id"])
                    rows["bills"].append(normalized)
            except ValidationError as exc:
                raise ValidationError(f"Row {line}: {exc}") from None
            if identity in seen:
                raise ValidationError(f"Row {line}: duplicate {kind} id in the same file.")
            seen.add(identity)
        if not any(rows.values()):
            raise ValidationError("CSV does not contain any records.")
        rows["legacy"] = False
        return rows
    except csv.Error as exc:
        raise ValidationError(f"CSV could not be read: {exc}") from None


def _minor_for_event(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError("All record amounts must be positive integer minor units.")
    return value


def _check_snapshot_currency(transactions, invoices, bills, policy):
    for collection in (transactions or [], invoices or [], bills or []):
        for row in collection:
            if normalize_currency(row.get("currency"), required=True) != PROBAHO_CURRENCY:
                raise ValidationError("This prototype supports BDT only; mixed currencies are not accepted.")
    if policy and normalize_currency(policy.get("currency"), required=True) != PROBAHO_CURRENCY:
        raise ValidationError("Policy currency must match BDT.")


def _parse_action(action):
    if not isinstance(action, dict):
        raise ValidationError("Plan action is invalid.")
    result = dict(action)
    result["action_id"] = result.get("action_id", result.get("id", ""))
    result["type"] = result.get("type", result.get("action_type", ""))
    if not isinstance(result["action_id"], str) or not result["action_id"]:
        raise ValidationError("Plan action id is required.")
    if "amount_minor" in result:
        result["amount_minor"] = _minor_for_event(result["amount_minor"])
    return result


def _safe_date_add(value: date, days: int, field="date") -> date:
    try:
        return value + timedelta(days=days)
    except (OverflowError, ValueError):
        raise ValidationError(f"{field} is outside the supported date range.") from None


def _projection_inputs(args, kwargs):
    """Normalize the explicit API shape and the old positional test shape."""
    if args:
        names = ("opening_cash_minor", "transactions", "invoices", "bills", "policy", "target_date", "scenario")
        for name, value in zip(names, args):
            kwargs.setdefault(name, value)
    opening = kwargs.get("opening_cash_minor", kwargs.get("opening_cash", 0))
    opening = nonnegative_minor(opening, "opening_cash_minor")
    target_text = valid_date(kwargs.get("target_date", ""), "target_date")
    target = date.fromisoformat(target_text)
    opening_text = valid_date(kwargs.get("opening_date") or target_text, "opening_date")
    opening_date = date.fromisoformat(opening_text)
    if target < opening_date:
        raise ValidationError("target_date cannot be before opening_date.")
    horizon = _safe_date_add(opening_date, MAX_PROJECTION_DAYS, "opening_date")
    if target > horizon:
        raise ValidationError("target_date exceeds the 366-day projection horizon.")
    scenario = kwargs.get("scenario", "base")
    if scenario not in SCENARIOS:
        raise ValidationError("scenario must be base, late_collection or approved_recovery.")
    transactions = list(kwargs.get("transactions") or [])
    invoices = list(kwargs.get("invoices") or [])
    bills = list(kwargs.get("bills") or [])
    policy = dict(kwargs.get("policy") or {"reserve_floor_minor": 0, "action_limit_minor": MAX_AMOUNT_MINOR,
                                            "currency": PROBAHO_CURRENCY, "payroll_priority": True})
    policy.setdefault("currency", PROBAHO_CURRENCY)
    if "reserve_floor_minor" not in policy:
        raw_reserve = policy.get("reserve_floor", 0)
        try:
            reserve_decimal = Decimal(str(raw_reserve).strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ValidationError("reserve_floor must be a non-negative amount.") from None
        if not reserve_decimal.is_finite() or reserve_decimal < 0 or reserve_decimal != reserve_decimal.quantize(Decimal("0.01")):
            raise ValidationError("reserve_floor must be a non-negative amount.")
        policy["reserve_floor_minor"] = int(reserve_decimal * 100)
    if "action_limit_minor" not in policy:
        raw_limit = policy.get("action_limit", MAX_AMOUNT_MINOR / 100)
        try:
            limit_decimal = Decimal(str(raw_limit).strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise ValidationError("action_limit must be a non-negative amount.") from None
        if not limit_decimal.is_finite() or limit_decimal < 0 or limit_decimal != limit_decimal.quantize(Decimal("0.01")):
            raise ValidationError("action_limit must be a non-negative amount.")
        policy["action_limit_minor"] = int(limit_decimal * 100)
    if policy.get("payroll_priority", True) is not True:
        raise ValidationError("payroll_priority must be true for this protected payroll prototype.")
    scoped_business = kwargs.get("business_id")
    if scoped_business is not None:
        validate_business_id(scoped_business)
        if policy.get("business_id") not in (None, "", scoped_business):
            raise ValidationError("Projection policy belongs to another business.")
    for collection in (transactions, invoices, bills):
        for row in collection:
            if not isinstance(row, dict):
                raise ValidationError("Projection records must be objects.")
            if scoped_business is not None and row.get("business_id") not in (None, "", scoped_business):
                raise ValidationError("Projection contains a record from another business.")
    _check_snapshot_currency(transactions, invoices, bills, policy)
    nonnegative_minor(policy["reserve_floor_minor"], "reserve_floor_minor")
    nonnegative_minor(policy["action_limit_minor"], "action_limit_minor")
    actions = kwargs.get("approved_actions") or kwargs.get("actions") or []
    if isinstance(actions, dict):
        actions = [actions]
    if not isinstance(actions, list):
        raise ValidationError("approved_actions must be a list.")
    return opening, target, opening_date, horizon, scenario, transactions, invoices, bills, policy, list(actions), scoped_business


def _record_scope(row, business_id):
    if business_id is not None and row.get("business_id") not in (None, "", business_id):
        raise ValidationError("Record belongs to another business.")
    normalize_currency(row.get("currency"), required=True)


def _action_scope(action, business_id):
    if not isinstance(action, dict):
        raise ValidationError("Plan action is invalid.")
    if business_id is not None and action.get("business_id") not in (None, "", business_id):
        raise ValidationError("Projection action belongs to another business.")
    normalize_currency(action.get("currency"), required=True)
    action_id = action.get("action_id", action.get("id"))
    if not isinstance(action_id, str) or not action_id:
        raise ValidationError("Plan action id is required.")
    return action_id


def project_cash(*args, **kwargs) -> dict:
    """Project scheduled cash using a bounded daily event ledger.

    ``opening_cash_minor`` is already the cash position at ``opening_date``;
    historical events are therefore validated but excluded.  Approved supplier
    recovery is represented as a split event: the deferred amount is removed
    from the original due date and added exactly once at the later date.
    """
    if args and hasattr(args[0], "snapshot"):
        store = args[0]
        if len(args) < 2:
            raise ValidationError("business_id is required for a Store projection.")
        scoped_business = args[1]
        scoped_date = args[2] if len(args) > 2 else kwargs.get("target_date")
        snapshot = store.snapshot(scoped_business)
        kwargs = {**kwargs, "business_id": scoped_business,
                  "opening_cash_minor": snapshot["business"]["opening_cash_minor"],
                  "opening_date": snapshot["business"]["opening_date"],
                  "transactions": snapshot["transactions"], "invoices": snapshot["invoices"],
                  "bills": snapshot["bills"], "policy": snapshot["policy"],
                  "target_date": scoped_date}
        accepted = [item for item in (snapshot["sandbox"].get("accepted_actions") or [])
                    if isinstance(item, dict) and item.get("type") in ("supplier_reschedule", "reschedule")]
        if not accepted:
            accepted = [
                {"action_id": item.get("action_id", f"accepted-{bill_id}"), "type": "supplier_reschedule",
                 "business_id": scoped_business, "bill_id": bill_id, "payee": item.get("payee"),
                 "amount_minor": item.get("amount_minor", 0), "currency": PROBAHO_CURRENCY,
                 "date": item.get("action_date", scoped_date), "reschedule_to": item.get("reschedule_to")}
                for bill_id, item in snapshot["sandbox"].get("rescheduled_bills", {}).items()
            ]
        if kwargs.get("scenario", "base") == "approved_recovery" and not kwargs.get("approved_actions") and not kwargs.get("actions"):
            kwargs["approved_actions"] = accepted
        args = ()
    opening, target, opening_date, horizon, scenario, transactions, invoices, bills, policy, actions, business_id = _projection_inputs(args, kwargs)
    reserve = policy["reserve_floor_minor"]
    action_limit = nonnegative_minor(policy["action_limit_minor"], "action_limit_minor")
    events = defaultdict(list)
    source_refs = [{"kind": "business", "id": business_id, "field": "opening_cash_minor",
                    "amount_minor": opening, "effect_minor": opening}]
    action_map = {}
    bill_actions = defaultdict(list)
    for raw_action in actions:
        action_id = _action_scope(raw_action, business_id)
        action = dict(raw_action)
        kind = action.get("type", action.get("action_type", ""))
        identity = (action_id, action.get("bill_id"), action.get("invoice_id"))
        if identity in action_map:
            raise ValidationError("Duplicate action for the same record is not allowed.")
        action_map[identity] = action
        if kind in ("supplier_reschedule", "reschedule"):
            if scenario != "approved_recovery":
                continue
            bill_id = action.get("bill_id")
            if not isinstance(bill_id, str) or not bill_id:
                raise ValidationError("Supplier reschedule requires bill_id.")
            amount = action.get("amount_minor")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise ValidationError("Deferred amount must be a positive integer minor-unit amount.")
            if amount > action_limit:
                raise ValidationError("Deferred amount exceeds the policy action limit.")
            action["amount_minor"] = amount
            bill_actions[bill_id].append(action)
        elif kind not in ("collection_reminder", "reminder"):
            raise ValidationError("Unsupported projection action type.")
    for row in transactions:
        _record_scope(row, business_id)
        day_text = valid_date(row.get("date", ""), "Transaction date")
        day = date.fromisoformat(day_text)
        amount = record_amount_minor(row)
        kind = row.get("type")
        if kind not in TRANSACTION_TYPES:
            raise ValidationError("Transaction type must be income or expense.")
        if not (opening_date <= day <= target):
            continue
        payroll = kind == "expense" and str(row.get("category", "")).strip().casefold() == "payroll"
        effect = amount if kind == "income" else -amount
        ref = {"kind": "transaction", "id": row.get("id"), "date": day_text,
               "amount_minor": amount, "effect_minor": effect, "payroll": payroll}
        events[day_text].append({"effect_minor": effect, "ref": ref, "payroll": payroll})
        source_refs.append(ref)
    for invoice in invoices:
        _record_scope(invoice, business_id)
        status = str(invoice.get("status", "confirmed")).strip().lower()
        if status not in INVOICE_STATUSES:
            raise ValidationError("Invoice status is invalid.")
        due_text = valid_date(invoice.get("due_date", ""), "invoice due_date")
        issue_text = valid_date(invoice.get("issue_date") or due_text, "issue_date")
        expected_text = valid_date(invoice.get("expected_collection_date") or invoice.get("due_date", ""), "expected_collection_date")
        issue = date.fromisoformat(issue_text)
        expected = date.fromisoformat(expected_text)
        if date.fromisoformat(due_text) < issue:
            raise ValidationError("Invoice due_date cannot be before issue_date.")
        if expected < issue:
            raise ValidationError("expected_collection_date cannot be before issue_date.")
        amount = record_amount_minor(invoice)
        # Paid/collected receipts are represented by settled transactions;
        # projecting them again would create cash from the same receipt twice.
        if status in ("paid", "collected", "cancelled", "disputed", "draft"):
            continue
        if expected < opening_date or expected > target:
            continue
        projected = expected
        if scenario == "late_collection":
            projected = _safe_date_add(expected, 7, "late collection date")
            if projected > target:
                continue
        projected_text = projected.isoformat()
        ref = {"kind": "invoice", "id": invoice.get("id"), "date": projected_text,
               "amount_minor": amount, "effect_minor": amount, "status": status}
        events[projected_text].append({"effect_minor": amount, "ref": ref})
        source_refs.append(ref)
    bill_by_id = {}
    for bill in bills:
        _record_scope(bill, business_id)
        status = str(bill.get("status", "open")).strip().lower()
        if status not in BILL_STATUSES:
            raise ValidationError("Bill status is invalid.")
        due_text = valid_date(bill.get("due_date", ""), "bill due_date")
        due = date.fromisoformat(due_text)
        amount = record_amount_minor(bill)
        priority = str(bill.get("priority", "normal")).strip().lower()
        if priority not in BILL_PRIORITIES:
            raise ValidationError("Bill priority is invalid.")
        if bill.get("id") in bill_by_id:
            raise ValidationError("Duplicate bill id is not allowed in a projection.")
        bill_by_id[bill.get("id")] = bill
        existing_date = bill.get("rescheduled_date")
        if status == "rescheduled":
            if not existing_date:
                raise ValidationError("Rescheduled bills require rescheduled_date.")
            existing_date = valid_date(existing_date, "rescheduled_date")
            if date.fromisoformat(existing_date) <= due:
                raise ValidationError("rescheduled_date must be later than due_date.")
            if date.fromisoformat(existing_date) > horizon:
                raise ValidationError("rescheduled_date exceeds the 366-day projection horizon.")
            if bill.get("id") in bill_actions:
                raise ValidationError("A bill already deferred cannot receive another deferral.")
        elif existing_date not in (None, ""):
            existing_date = valid_date(existing_date, "rescheduled_date")
            if date.fromisoformat(existing_date) <= due:
                raise ValidationError("rescheduled_date must be later than due_date.")
            if date.fromisoformat(existing_date) > horizon:
                raise ValidationError("rescheduled_date exceeds the 366-day projection horizon.")
        group = bill_actions.get(bill.get("id"), [])
        if existing_date and group:
            raise ValidationError("A bill already deferred cannot receive another deferral.")
        deferred_total = sum(item["amount_minor"] for item in group)
        if deferred_total > amount:
            raise ValidationError("Duplicate supplier actions cannot defer more than the bill amount.")
        for item in group:
            if not _flag(bill.get("reschedule_allowed", bill.get("reschedulable", False)), "reschedule_allowed"):
                raise ValidationError("This supplier bill is not reschedulable.")
            if priority == "payroll":
                raise ValidationError("Payroll-priority bills cannot be rescheduled.")
            if item.get("payee") not in (None, "", bill.get("payee")):
                raise ValidationError("Supplier payee does not match the bill.")
            if item.get("original_amount_minor") not in (None, amount):
                raise ValidationError("Supplier bill amount changed.")
            if item.get("original_due_date") not in (None, due_text):
                raise ValidationError("Supplier bill date changed.")
            new_text = item.get("reschedule_to", item.get("new_due_date"))
            if not new_text:
                raise ValidationError("Supplier reschedule requires a later date.")
            new_text = valid_date(new_text, "reschedule_to")
            new_day = date.fromisoformat(new_text)
            if new_day <= due:
                raise ValidationError("reschedule_to must be later than the original due_date.")
            if new_day > horizon:
                raise ValidationError("reschedule_to exceeds the 366-day projection horizon.")
            item["reschedule_to"] = new_text
        if status in ("paid", "cancelled"):
            if group:
                raise ValidationError("Paid or cancelled bills cannot be rescheduled.")
            continue
        if existing_date:
            event_text = existing_date
            if opening_date <= date.fromisoformat(event_text) <= target:
                ref = {"kind": "bill", "id": bill.get("id"), "date": event_text,
                       "amount_minor": amount, "effect_minor": -amount,
                       "payroll": priority == "payroll"}
                events[event_text].append({"effect_minor": -amount, "ref": ref, "payroll": priority == "payroll"})
                source_refs.append(ref)
            continue
        remaining = amount - deferred_total
        if opening_date <= due <= target and remaining:
            ref = {"kind": "bill", "id": bill.get("id"), "date": due_text,
                   "amount_minor": remaining, "effect_minor": -remaining,
                   "payroll": priority == "payroll"}
            events[due_text].append({"effect_minor": -remaining, "ref": ref, "payroll": priority == "payroll"})
            source_refs.append(ref)
        for item in group:
            deferred_text = item["reschedule_to"]
            deferred_amount = item["amount_minor"]
            if opening_date <= date.fromisoformat(deferred_text) <= target:
                ref = {"kind": "bill_deferred", "id": bill.get("id"), "date": deferred_text,
                       "amount_minor": deferred_amount, "effect_minor": -deferred_amount,
                       "payroll": priority == "payroll"}
                events[deferred_text].append({"effect_minor": -deferred_amount, "ref": ref, "payroll": priority == "payroll"})
                source_refs.append(ref)
    unknown_action_bills = sorted(set(bill_actions) - set(bill_by_id))
    if unknown_action_bills:
        raise ValidationError("Supplier reschedule references an unknown bill.")
    days = []
    balance = opening
    for offset in range((target - opening_date).days + 1):
        cursor = opening_date + timedelta(days=offset)
        day_text = cursor.isoformat()
        day_events = events.get(day_text, [])
        inflow = sum(item["effect_minor"] for item in day_events if item["effect_minor"] > 0)
        outflow = sum(-item["effect_minor"] for item in day_events if item["effect_minor"] < 0)
        opening_day = balance
        balance += inflow - outflow
        days.append({"date": day_text, "opening_cash_minor": opening_day,
                     "inflow_minor": inflow, "outflow_minor": outflow,
                     "closing_cash_minor": balance,
                     "source_references": [item["ref"] for item in day_events]})
    if not days:
        raise ValidationError("Projection horizon is empty.")
    closings = [opening] + [day["closing_cash_minor"] for day in days]
    minimum_cash = min(closings)
    daily_shortfalls = [(max(0, reserve - value), opening_date if index == 0 else date.fromisoformat(days[index - 1]["date"]))
                        for index, value in enumerate(closings)]
    worst_shortfall = max(shortfall_value for shortfall_value, _ in daily_shortfalls)
    first_shortfall_date = min((day for shortfall_value, day in daily_shortfalls if shortfall_value > 0), default=None)
    payroll_outflow = sum(ref["amount_minor"] for ref in source_refs if ref.get("payroll"))
    total_inflow = sum(day["inflow_minor"] for day in days)
    total_outflow = sum(day["outflow_minor"] for day in days)
    if opening + total_inflow - total_outflow != balance:
        raise ValidationError("Projection daily totals do not reconcile.")
    closing_shortfall = max(0, reserve - balance)
    return {"business_id": business_id, "target_date": target.isoformat(), "opening_date": opening_date.isoformat(),
            "currency": PROBAHO_CURRENCY, "scenario": scenario, "opening_cash_minor": opening,
            "closing_cash_minor": balance, "minimum_cash_minor": minimum_cash,
            "reserve_floor_minor": reserve, "reserve_shortfall_minor": closing_shortfall,
            "minimum_reserve_shortfall_minor": worst_shortfall, "maximum_reserve_shortfall_minor": worst_shortfall,
            "closing_reserve_shortfall_minor": closing_shortfall,
            "cash_gap_minor": worst_shortfall, "gap_minor": worst_shortfall,
            "first_shortfall_date": first_shortfall_date.isoformat() if first_shortfall_date else None,
            "payroll_outflow_minor": payroll_outflow, "total_inflow_minor": total_inflow,
            "total_outflow_minor": total_outflow, "inflow_minor": total_inflow, "outflow_minor": total_outflow,
            "source_references": source_refs, "days": days,
            "assumptions": {"late_collection_days": 7 if scenario == "late_collection" else 0,
                            "reminders_are_not_collections": True,
                            "scheduled_projection_not_bank_balance": True,
                            "horizon_days_after_opening": MAX_PROJECTION_DAYS}}


def compute_cash_gap(projection=None, *args, **kwargs) -> dict:
    """Return the reserve gap for a projection or build one from inputs."""
    if not isinstance(projection, dict) or "closing_cash_minor" not in projection:
        if projection is not None:
            args = (projection,) + args
        projection = project_cash(*args, **kwargs)
    reserve = projection.get("reserve_floor_minor", 0)
    closing = projection.get("closing_cash_minor", 0)
    minimum = projection.get("minimum_cash_minor", closing)
    if not isinstance(reserve, int) or not isinstance(closing, int) or not isinstance(minimum, int):
        raise ValidationError("Projection cash values must be integer minor units.")
    shortfall = projection.get("minimum_reserve_shortfall_minor", max(0, reserve - minimum))
    if not isinstance(shortfall, int) or shortfall < 0:
        raise ValidationError("Projection reserve values must be non-negative integer minor units.")
    return {"business_id": projection.get("business_id"), "target_date": projection.get("target_date"),
            "currency": PROBAHO_CURRENCY, "closing_cash_minor": closing,
            "minimum_cash_minor": minimum,
            "reserve_floor_minor": reserve, "reserve_shortfall_minor": shortfall,
            "cash_gap_minor": shortfall, "gap_minor": shortfall,
            "shortfall": shortfall > 0,
            "first_shortfall_date": projection.get("first_shortfall_date"),
            "source_references": projection.get("source_references", [])}


def _next_date(value, days=7):
    return _safe_date_add(date.fromisoformat(valid_date(value)), days, "reschedule_to").isoformat()


def compare_plans(*args, **kwargs) -> dict:
    """Build explainable collection, reschedule and mock-financing options."""
    if args and hasattr(args[0], "snapshot"):
        store = args[0]
        if len(args) < 2:
            raise ValidationError("business_id is required for plan comparison.")
        scoped_business = args[1]
        scoped_date = args[2] if len(args) > 2 else kwargs.get("target_date")
        snapshot = store.snapshot(scoped_business)
        kwargs = {**kwargs, "business_id": scoped_business, "target_date": scoped_date,
                  "opening_cash_minor": snapshot["business"]["opening_cash_minor"],
                  "opening_date": snapshot["business"]["opening_date"],
                  "transactions": snapshot["transactions"], "invoices": snapshot["invoices"],
                  "bills": snapshot["bills"], "policy": snapshot["policy"]}
        kwargs["snapshot_hash"] = snapshot.get("snapshot_hash")
        accepted = [item for item in (snapshot["sandbox"].get("accepted_actions") or [])
                    if isinstance(item, dict) and item.get("type") in ("supplier_reschedule", "reschedule")]
        if not accepted:
            accepted = [
                {"action_id": item.get("action_id", f"accepted-{bill_id}"), "type": "supplier_reschedule",
                 "business_id": scoped_business, "bill_id": bill_id, "payee": item.get("payee"),
                 "amount_minor": item.get("amount_minor", 0), "currency": PROBAHO_CURRENCY,
                 "date": item.get("action_date", scoped_date), "reschedule_to": item.get("reschedule_to")}
                for bill_id, item in snapshot["sandbox"].get("rescheduled_bills", {}).items()
            ]
        kwargs["accepted_actions"] = accepted
        args = ()
    # Accept a projection as the first positional argument, or explicit
    # keyword snapshots.  The Store-facing code supplies the latter.
    projection = kwargs.pop("projection", None)
    if args and isinstance(args[0], dict) and "closing_cash_minor" in args[0]:
        projection = args[0]
        args = args[1:]
    if projection is None:
        projection = project_cash(*args, **kwargs)
    requested_business = kwargs.get("business_id")
    if projection.get("business_id") and requested_business not in (None, "", projection.get("business_id")):
        raise ValidationError("Plan projection belongs to another business.")
    business_id = projection.get("business_id") or requested_business
    target = valid_date(projection.get("target_date", ""), "target_date")
    opening_date = valid_date(projection.get("opening_date", target), "opening_date")
    transactions = kwargs.get("transactions", [])
    invoices = kwargs.get("invoices", [])
    bills = kwargs.get("bills", [])
    policy = kwargs.get("policy", {"reserve_floor_minor": projection.get("reserve_floor_minor", 0),
                                     "action_limit_minor": MAX_AMOUNT_MINOR, "currency": PROBAHO_CURRENCY})
    accepted_actions = kwargs.get("accepted_actions") or kwargs.get("approved_actions") or kwargs.get("actions") or []
    accepted_bill_ids = {item.get("bill_id") for item in accepted_actions if isinstance(item, dict) and item.get("bill_id")}
    gap = compute_cash_gap(projection)
    accepted_projection = None
    effective_gap = gap
    if accepted_actions:
        accepted_projection = project_cash(opening_cash_minor=projection["opening_cash_minor"],
                                           opening_date=opening_date, transactions=transactions,
                                           invoices=invoices, bills=bills, policy=policy,
                                           target_date=target, scenario="approved_recovery",
                                           approved_actions=accepted_actions, business_id=business_id)
        effective_gap = compute_cash_gap(accepted_projection)
    actions = []
    invoice_candidates = sorted(
        (row for row in invoices
         if str(row.get("status", "")).strip().lower() in ("confirmed", "overdue") and row.get("amount_minor", 0) > 0
         and opening_date <= valid_date(row.get("expected_collection_date") or row.get("due_date", ""), "expected_collection_date") <= target),
        key=lambda row: (row.get("expected_collection_date") or row.get("due_date", ""), str(row.get("id", ""))))
    invoice = invoice_candidates[0] if invoice_candidates else None
    if invoice:
        actions.append({"action_id": "collection-reminder", "type": "collection_reminder",
                        "label": "Collection reminder (no cash recognized)",
                        "invoice_id": invoice.get("id"), "payee": invoice.get("customer"),
                        "amount_minor": invoice.get("amount_minor"), "currency": PROBAHO_CURRENCY,
                        "date": target, "original_expected_collection_date": invoice.get("expected_collection_date"),
                        "cash_effect_minor": 0, "executable": True,
                        "feasible": True,
                        "explanation": "Creates a reminder draft only. A reminder is not a collected receivable."})
    else:
        actions.append({"action_id": "collection-reminder", "type": "collection_reminder",
                        "label": "Collection reminder (no confirmed receivable)",
                        "amount_minor": 0, "currency": PROBAHO_CURRENCY, "date": target,
                        "cash_effect_minor": 0, "executable": False, "feasible": False,
                        "reason": "No confirmed receivable is available."})

    limit = policy.get("action_limit_minor", MAX_AMOUNT_MINOR)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValidationError("action_limit_minor must be a non-negative integer.")
    candidate_rows = []
    for bill in bills:
        status = str(bill.get("status", "open")).strip().lower()
        due_text = valid_date(bill.get("due_date", ""), "bill due_date")
        priority = str(bill.get("priority", "normal")).strip().lower()
        if (opening_date <= due_text <= target and status in ("open", "scheduled") and
                _flag(bill.get("reschedule_allowed", bill.get("reschedulable", False)), "reschedule_allowed") and
                priority != "payroll" and bill.get("id") not in accepted_bill_ids and
                not bill.get("rescheduled_date")):
            try:
                reschedule_to = _next_date(target, 7)
            except ValidationError:
                continue
            if date.fromisoformat(reschedule_to) > _safe_date_add(date.fromisoformat(opening_date), MAX_PROJECTION_DAYS, "opening_date"):
                continue
            amount = min(int(bill.get("amount_minor", 0)), 4_000_000, limit)
            if amount > 0:
                candidate_rows.append((due_text, str(bill.get("id", "")), bill, amount, reschedule_to))
    candidate_rows.sort(key=lambda item: (item[0], item[1]))
    chosen = None
    evaluations = []
    for _due_text, _bill_id, bill, amount, reschedule_to in candidate_rows:
        recovery_actions = [{"action_id": "supplier-reschedule", "type": "supplier_reschedule",
                             "label": "Supplier reschedule (assumption; consent required)",
                             "bill_id": bill.get("id"), "payee": bill.get("payee"),
                             "amount_minor": amount, "original_amount_minor": bill.get("amount_minor"), "currency": PROBAHO_CURRENCY,
                             "date": target, "original_due_date": bill.get("due_date"), "reschedule_to": reschedule_to,
                             "cash_effect_minor": amount, "executable": True}]
        recovered = project_cash(opening_cash_minor=projection["opening_cash_minor"],
                                 opening_date=opening_date, transactions=transactions, invoices=invoices, bills=bills,
                                 policy=policy, target_date=target,
                                 scenario="approved_recovery", approved_actions=list(accepted_actions) + recovery_actions,
                                 business_id=business_id)
        recovered_gap = compute_cash_gap(recovered)
        feasible = (amount <= limit and recovered["minimum_reserve_shortfall_minor"] == 0 and
                     recovered["payroll_outflow_minor"] >= projection.get("payroll_outflow_minor", 0))
        evaluation = {"bill_id": bill.get("id"), "amount_minor": amount,
                      "projected_closing_cash_minor": recovered["closing_cash_minor"],
                      "projected_minimum_cash_minor": recovered["minimum_cash_minor"],
                      "projected_reserve_shortfall_minor": recovered_gap["reserve_shortfall_minor"],
                      "feasible": feasible}
        evaluations.append(evaluation)
        if feasible and chosen is None:
            chosen = (recovery_actions[0], recovered, recovered_gap)
    if chosen:
        recovery_action, recovered, recovered_gap = chosen
        actions[1:1] = [{**recovery_action, "feasible": True,
                         "projected_closing_cash_minor": recovered["closing_cash_minor"],
                         "projected_minimum_cash_minor": recovered["minimum_cash_minor"],
                         "projected_reserve_shortfall_minor": recovered_gap["reserve_shortfall_minor"],
                         "explanation": "Moves only the approved supplier amount after the target date; supplier consent is still required."}]
    elif evaluations:
        best = max(evaluations, key=lambda item: (item["projected_minimum_cash_minor"], -item["amount_minor"], str(item["bill_id"])))
        actions.append({"action_id": "supplier-reschedule", "type": "supplier_reschedule",
                        "label": "Supplier reschedule (not feasible under current constraints)",
                        "bill_id": best["bill_id"], "amount_minor": best["amount_minor"],
                        "currency": PROBAHO_CURRENCY, "date": target, "cash_effect_minor": best["amount_minor"],
                        "executable": False, "feasible": False,
                        "projected_closing_cash_minor": best["projected_closing_cash_minor"],
                        "projected_minimum_cash_minor": best["projected_minimum_cash_minor"],
                        "projected_reserve_shortfall_minor": best["projected_reserve_shortfall_minor"],
                        "reason": "No candidate protects the reserve floor on every projected day."})
    else:
        actions.append({"action_id": "supplier-reschedule", "type": "supplier_reschedule",
                        "label": "Supplier reschedule (unavailable)", "amount_minor": 0,
                        "currency": PROBAHO_CURRENCY, "date": target, "cash_effect_minor": 0,
                        "executable": False, "feasible": False,
                        "reason": "No non-paid reschedulable supplier bill is available."})

    gap_amount = effective_gap["reserve_shortfall_minor"]
    for action_id, label, fee_bps, term in (("mock-financing-invoice-advance", "MOCK financing: invoice advance", 200, "30 days"),
                                             ("mock-financing-working-capital", "MOCK financing: working-capital line", 350, "60 days")):
        principal = gap_amount
        fee = principal * fee_bps // 10_000
        actions.append({"action_id": action_id, "type": "mock_financing", "label": label,
                        "amount_minor": principal, "principal_minor": principal, "currency": PROBAHO_CURRENCY,
                        "cash_effect_minor": principal, "fee_minor": fee, "term": term,
                        "repayment_minor": principal + fee, "policy_limit_minor": limit,
                        "feasible": bool(principal) and principal <= limit, "executable": False, "mock": True,
                        "assumptions": {"fee_bps": fee_bps, "eligibility": "illustrative only",
                                        "repayment": principal + fee},
                        "explanation": "Catalogue comparison only; no lender, credit decision or money movement is connected."})
    result = {"business_id": business_id, "target_date": target, "currency": PROBAHO_CURRENCY,
              "base_gap": gap, "plans": actions,
              "current_gap": effective_gap,
              "policy_version": policy.get("version"),
              "constraints": {"reserve_floor_minor": projection["reserve_floor_minor"],
                              "payroll_priority": policy.get("payroll_priority", True),
                              "action_limit_minor": policy.get("action_limit_minor", MAX_AMOUNT_MINOR)},
              "source_references": projection.get("source_references", []),
              "candidate_evaluations": evaluations,
              "explanation": "Plans are deterministic scenarios linked to ledger rows; mock financing is labelled and never executable."}
    if kwargs.get("snapshot_hash"):
        result["snapshot_hash"] = kwargs["snapshot_hash"]
    if accepted_projection is not None:
        result["approved_recovery_projection"] = accepted_projection
    for action in actions:
        action["business_id"] = business_id
        action.setdefault("kind", action.get("type"))
        action.setdefault("action_type", action.get("type"))
    result["options"] = actions
    result["collection_reminder"] = next((item for item in actions if item.get("type") == "collection_reminder"), None)
    result["supplier_reschedule"] = next((item for item in actions if item.get("type") in ("supplier_reschedule", "reschedule")), None)
    result["financing_alternatives"] = [item for item in actions if item.get("type") == "mock_financing"]
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["plan_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return result


# ---------------------------------------------------------------------------
# Legacy personal-finance helpers retained for the original demo and tests.

CATEGORIES = ("Housing", "Groceries", "Dining", "Transport", "Utilities",
              "Subscriptions", "Shopping", "Health", "Education", "Other")
KEYWORDS = {
    "Housing": ("rent", "ভাড়া", "ভাড়া", "housing"),
    "Groceries": ("grocery", "groceries", "supermarket", "shwapno", "বাজার"),
    "Dining": ("restaurant", "coffee", "cafe", "foodpanda", "lunch", "dinner", "খাবার"),
    "Transport": ("uber", "pathao", "bus", "rickshaw", "transport", "যাতায়াত"),
    "Utilities": ("electric", "internet", "water", "gas bill", "utility", "বিদ্যুৎ"),
    "Subscriptions": ("netflix", "spotify", "subscription", "github", "youtube premium"),
    "Shopping": ("daraz", "shopping", "clothes", "bookshop"),
    "Health": ("pharmacy", "doctor", "medicine", "hospital", "ওষুধ"),
    "Education": ("tuition", "course", "university", "education", "টিউশন"),
}


def month_value(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        raise ValidationError("Month must use YYYY-MM.")
    try:
        date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise ValidationError("Month is not valid.") from exc
    return value


def previous_month(month: str) -> str:
    year, number = map(int, month_value(month).split("-"))
    return f"{year - (number == 1):04d}-{12 if number == 1 else number - 1:02d}"


def categorize(description: str, kind: str) -> str:
    if kind == "income":
        return "Income"
    text = description.casefold()
    for category, terms in KEYWORDS.items():
        if any(term in text for term in terms):
            return category
    return "Other"


def validate_transaction(raw: dict) -> dict:
    """Legacy transaction shape (amount in BDT) with a deterministic fingerprint."""
    if not isinstance(raw, dict):
        raise ValidationError("Each transaction must be an object.")
    day = raw.get("date", "")
    if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValidationError("Date must use YYYY-MM-DD.")
    try:
        date.fromisoformat(day)
    except ValueError:
        raise ValidationError("Transaction date is not valid.") from None
    description = raw.get("description", "")
    if not isinstance(description, str):
        raise ValidationError("Description must be text.")
    description = description.strip()
    if not description or len(description) > 300 or any(ord(c) < 32 for c in description):
        raise ValidationError("Description must contain 1-300 printable characters.")
    kind = raw.get("type", "")
    if not isinstance(kind, str) or kind.strip().lower() not in ("income", "expense"):
        raise ValidationError("Type must be income or expense.")
    kind = kind.strip().lower()
    currency = raw.get("currency", "BDT") or "BDT"
    if not isinstance(currency, str) or currency.strip().upper() != "BDT":
        raise ValidationError("This prototype supports BDT only; mixed currencies are not accepted.")
    amount = money_minor(raw.get("amount", ""))
    category = raw.get("category", "") or categorize(description, kind)
    if category not in (*CATEGORIES, "Income") or (kind == "expense" and category == "Income"):
        raise ValidationError("Choose a supported expense category.")
    if kind == "income":
        category = "Income"
    normalized = " ".join(description.casefold().split())
    fingerprint = hashlib.sha256(f"{day}|{normalized}|{kind}|{amount}".encode()).hexdigest()
    return {"date": day, "description": description, "type": kind,
            "amount_minor": amount, "category": category, "currency": "BDT",
            "fingerprint": fingerprint, "business_id": raw.get("business_id")}


def parse_csv(text: str) -> list[dict]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1_500_000:
        raise ValidationError("CSV must be UTF-8 text and no larger than 1.5 MB.")
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        if reader.fieldnames:
            reader.fieldnames = [field.strip() if isinstance(field, str) else field for field in reader.fieldnames]
        required = {"date", "description", "amount", "type"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValidationError("CSV needs date,description,amount,type columns. category and currency are optional.")
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValidationError("Duplicate CSV column names are not allowed.")
        rows = []
        for line, raw in enumerate(reader, 2):
            if len(rows) >= 5000:
                raise ValidationError("Import at most 5,000 rows at a time.")
            if None in raw:
                raise ValidationError(f"Row {line}: too many columns.")
            try:
                rows.append(validate_transaction(raw))
            except ValidationError as exc:
                raise ValidationError(f"Row {line}: {exc}") from None
    except csv.Error as exc:
        raise ValidationError(f"CSV could not be read: {exc}") from None
    if not rows:
        raise ValidationError("CSV does not contain any transactions.")
    return rows


def summary(rows: list[dict], month: str) -> dict:
    month_value(month)
    selected = [r for r in rows if r["date"].startswith(month)]
    income = sum(r["amount_minor"] for r in selected if r["type"] == "income")
    expense = sum(r["amount_minor"] for r in selected if r["type"] == "expense")
    categories = []
    for category in CATEGORIES:
        matches = [r for r in selected if r["type"] == "expense" and r["category"] == category]
        value = sum(r["amount_minor"] for r in matches)
        if matches:
            categories.append({"name": category, "amount_minor": value, "count": len(matches)})
    categories.sort(key=lambda item: item["amount_minor"], reverse=True)
    year, number = map(int, month.split("-"))
    daily = [{"day": day, "income_minor": 0, "expense_minor": 0}
             for day in range(1, calendar.monthrange(year, number)[1] + 1)]
    for row in selected:
        daily[int(row["date"][-2:]) - 1][row["type"] + "_minor"] += row["amount_minor"]
    return {"month": month, "currency": "BDT", "income_minor": income,
            "expense_minor": expense, "net_minor": income - expense,
            "savings_rate": round((income - expense) / income * 100, 1) if income else None,
            "transaction_count": len(selected), "categories": categories, "daily": daily}


def insights(rows: list[dict], month: str, target_percent: float = 20) -> list[dict]:
    current = summary(rows, month)
    prior = summary(rows, previous_month(month))
    result = []
    if not current["transaction_count"]:
        return [{"severity": "info", "title": "Your story starts here",
                 "body": "Import transactions or load the fictional sample workspace to begin."}]
    if not current["income_minor"]:
        result.append({"severity": "warning", "title": "Add your income",
                       "body": "No income is recorded this month. Savings rate and income-based budgets need an income value."})
    elif current["net_minor"] < 0:
        result.append({"severity": "warning", "title": "Expenses exceed income",
                       "body": f"Recorded spending exceeds recorded income by BDT {abs(current['net_minor']) / 100:,.2f}. Check for missing income and review flexible expenses."})
    elif current["savings_rate"] < target_percent:
        result.append({"severity": "warning", "title": "Your savings goal needs attention",
                       "body": f"Your recorded savings rate is {current['savings_rate']}%, below the selected {target_percent:g}% goal. This describes recorded cash flow, not a bank balance."})
    else:
        result.append({"severity": "positive", "title": "Room to build your savings",
                       "body": f"You have retained {current['savings_rate']}% of recorded income so far. A budget can reserve part of that amount for your chosen goal."})
    selected = [r for r in rows if r["date"].startswith(month) and r["type"] == "expense"]
    pairs = defaultdict(list)
    for row in selected:
        pairs[(row["description"].casefold(), row["amount_minor"])].append(row)
    if any(len(group) > 1 for group in pairs.values()):
        result.append({"severity": "warning", "title": "Check repeated charges",
                       "body": "The same description and amount occur more than once this month. These may be valid purchases; review the ledger before taking action."})
    flexible = [c for c in current["categories"] if c["name"] in ("Dining", "Shopping", "Subscriptions")]
    if flexible:
        biggest = max(flexible, key=lambda c: c["amount_minor"])
        result.append({"severity": "info", "title": f"One small change: {biggest['name'].lower()}",
                       "body": f"A 10% reduction in this month's recorded {biggest['name'].lower()} spending would free BDT {biggest['amount_minor'] / 1000:,.2f}. This is a scenario you can choose, not a guaranteed saving."})
    prior_categories = {c["name"]: c["amount_minor"] for c in prior["categories"]}
    for category in current["categories"]:
        old = prior_categories.get(category["name"], 0)
        if old and category["amount_minor"] > old * 1.2:
            change = round((category["amount_minor"] / old - 1) * 100)
            result.append({"severity": "info", "title": f"{category['name']} is up {change}%",
                           "body": "Compared with the previous calendar month's recorded total. Partial months and missing transactions can affect this comparison."})
            break
    return result[:4]


def recurring_bills(rows: list[dict], month: str) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        if row["type"] == "expense" and row["date"][:7] <= month and row["category"] in ("Housing", "Utilities", "Subscriptions", "Education", "Health"):
            groups[(" ".join(row["description"].casefold().split()), row["category"])].append(row)
    result = []
    for (_, category), group in groups.items():
        months = {row["date"][:7] for row in group}
        recent = sorted(group, key=lambda r: r["date"], reverse=True)
        if len(months) >= 2 and recent[0]["date"].startswith(month):
            result.append({"description": recent[0]["description"], "category": category,
                           "amount_minor": recent[0]["amount_minor"], "observed_months": len(months),
                           "last_date": recent[0]["date"], "confidence": "Pattern detected; verify manually"})
    return sorted(result, key=lambda r: r["amount_minor"], reverse=True)[:8]


def build_budget(rows: list[dict], month: str, income, savings_percent=20) -> dict:
    month_value(month)
    income_minor = money_minor(income)
    if isinstance(savings_percent, bool):
        raise ValidationError("Savings percentage must be a number between 0 and 80.")
    try:
        goal = Decimal(str(savings_percent))
    except InvalidOperation:
        raise ValidationError("Savings percentage must be a number.") from None
    if not goal.is_finite() or not 0 <= goal <= 80:
        raise ValidationError("Savings percentage must be between 0 and 80.")
    savings_minor = int(Decimal(income_minor) * goal / 100)
    available = income_minor - savings_minor
    prior = summary(rows, previous_month(month))
    reference = prior if prior["expense_minor"] else summary(rows, month)
    observed = {c["name"]: c["amount_minor"] for c in reference["categories"]}
    fixed = ("Housing", "Utilities", "Education", "Health")
    protected = {category: observed.get(category, 0) for category in fixed}
    essential_total = sum(protected.values())
    if essential_total > available:
        raise ValidationError("Recorded essential spending exceeds the spending allowance. Choose a lower savings goal or correct the income/reference data.")
    flexible = [category for category in CATEGORIES if category not in fixed]
    defaults = {"Groceries": 12, "Dining": 6, "Transport": 8, "Subscriptions": 3, "Shopping": 6, "Other": 8}
    weights = {category: observed.get(category, 0) or max(1, income_minor * defaults[category] // 100) for category in flexible}
    total_weight = sum(weights.values())
    remainder = available - essential_total
    allocations = dict(protected)
    remaining = remainder
    for index, category in enumerate(flexible):
        value = remaining if index == len(flexible) - 1 else remainder * weights[category] // total_weight
        allocations[category] = value
        remaining -= value
    return {"month": month, "currency": "BDT", "income_minor": income_minor,
            "savings_percent": float(goal), "savings_minor": savings_minor,
            "spending_minor": available, "reference_month": reference["month"],
            "allocations": [{"category": c, "amount_minor": allocations[c]} for c in CATEGORIES],
            "explanation": "Uses recorded essential costs from the previous month when available, otherwise the selected month. Distributes the remaining allowance using observed flexible spending, with default weights for unseen categories. Review every allocation before approval."}
