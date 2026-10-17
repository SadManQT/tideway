"""Validated business records for Tideway.

Every monetary value ending in ``_minor`` is an integer number of minor units
(for example paisa for BDT or fen for CNY).  Human-facing amounts are parsed
from decimal text exactly once, at the boundary.  A business has exactly one
currency and every record, policy and action must match it.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


class ValidationError(ValueError):
    """A user-correctable input, scope or policy error."""


class SecurityError(ValidationError):
    """A refusal that may indicate tampering or abuse; counts toward the circuit breaker."""

    def __init__(self, code, message):
        super().__init__(f"{code}: {message}")
        self.code = code


# ISO 4217 currencies with two minor digits that the sandbox accepts.  A
# business still uses exactly one of them; mixed currencies are rejected.
# Zero-decimal currencies (JPY, KRW, VND...) are not supported yet: amounts are
# stored in hundredths.  Rates are illustrative units per US dollar, used only to
# show amounts in another currency for reading; they never enter any calculation.
CURRENCIES = {
    "USD": ("US dollar", 1), "EUR": ("Euro", 0.86), "GBP": ("Pound sterling", 0.75), "CHF": ("Swiss franc", 0.80),
    "CNY": ("Chinese yuan", 7.1), "HKD": ("Hong Kong dollar", 7.8), "SGD": ("Singapore dollar", 1.29),
    "MYR": ("Malaysian ringgit", 4.2), "THB": ("Thai baht", 33), "PHP": ("Philippine peso", 57),
    "IDR": ("Indonesian rupiah", 16_300), "INR": ("Indian rupee", 88), "BDT": ("Bangladeshi taka", 122),
    "PKR": ("Pakistani rupee", 282), "LKR": ("Sri Lankan rupee", 300), "NPR": ("Nepalese rupee", 140),
    "AED": ("UAE dirham", 3.67), "SAR": ("Saudi riyal", 3.75), "QAR": ("Qatari riyal", 3.64),
    "TRY": ("Turkish lira", 41), "EGP": ("Egyptian pound", 48), "KES": ("Kenyan shilling", 129),
    "NGN": ("Nigerian naira", 1_500), "ZAR": ("South African rand", 18), "BRL": ("Brazilian real", 5.4),
    "MXN": ("Mexican peso", 18.5), "CAD": ("Canadian dollar", 1.38), "AUD": ("Australian dollar", 1.52),
    "NZD": ("New Zealand dollar", 1.68),
}
# Large enough for high-denomination currencies (IDR, NGN) while bounding integer sizes.
MAX_UNITS = Decimal("1000000000000")
MAX_AMOUNT_MINOR = int(MAX_UNITS * 100)
MAX_PROJECTION_DAYS = 366
BUSINESS_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
RECORD_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
ACCOUNT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 -]{3,39}\Z")
TRANSACTION_TYPES = ("income", "expense")
INVOICE_STATUSES = ("draft", "confirmed", "overdue", "paid", "collected", "cancelled", "disputed")
OPEN_INVOICE_STATUSES = ("confirmed", "overdue")
SETTLED_INVOICE_STATUSES = ("paid", "collected")
BILL_STATUSES = ("open", "scheduled", "rescheduled", "paid", "cancelled")
OPEN_BILL_STATUSES = ("open", "scheduled", "rescheduled")
BILL_PRIORITIES = ("payroll", "critical", "high", "normal", "low")
AUTONOMY_LEVELS = ("advise", "propose", "delegate")


# ---------------------------------------------------------------------------
# Primitive parsing


def valid_date(value, field="date") -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ValidationError(f"{field} must use YYYY-MM-DD.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} is not a real calendar date.") from None
    if not 2000 <= parsed.year <= 2099:
        raise ValidationError(f"{field} must be between 2000 and 2099.")
    return value


def add_days(value: str, days: int, field="date") -> str:
    try:
        return (date.fromisoformat(valid_date(value, field)) + timedelta(days=days)).isoformat()
    except (OverflowError, ValueError):
        raise ValidationError(f"{field} is outside the supported date range.") from None


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def validate_business_id(value) -> str:
    if not isinstance(value, str) or not BUSINESS_ID_RE.fullmatch(value):
        raise ValidationError("business_id must contain 1-64 letters, numbers, '_' or '-'.")
    return value


USERNAME_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,31}\Z")


def validate_username(value) -> str:
    if not isinstance(value, str) or not USERNAME_RE.fullmatch(value.strip().lower()):
        raise ValidationError("Username must be 3-32 characters: lowercase letters, digits, '.', '_' or '-'.")
    return value.strip().lower()


def check_new_pin(pin) -> str:
    """New accounts need a 6-12 digit PIN that is not a repeated digit or a simple sequence."""
    if not isinstance(pin, str) or not pin.isdigit() or not 6 <= len(pin) <= 12:
        raise ValidationError("Choose a PIN of 6-12 digits.")
    steps = {int(b) - int(a) for a, b in zip(pin, pin[1:])}
    if len(set(pin)) == 1 or steps in ({1}, {-1}):
        raise ValidationError("That PIN is too easy to guess (repeated or sequential digits).")
    return pin


def validate_record_id(value, label="Record id") -> str:
    if not isinstance(value, str) or not RECORD_ID_RE.fullmatch(value):
        raise ValidationError(f"{label} must contain 1-80 safe characters.")
    return value


def normalize_currency(value, expected=None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("Currency is required.")
    code = value.strip().upper()
    if code not in CURRENCIES:
        raise ValidationError(f"Currency {code[:8]} is not supported. Use one of: {', '.join(sorted(CURRENCIES))}.")
    if expected is not None and code != expected:
        raise ValidationError(f"This business uses {expected}; mixed currencies are not accepted.")
    return code


def _decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"{field} must be a monetary value.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValidationError(f"{field} must be a number.") from None
    if not amount.is_finite():
        raise ValidationError(f"{field} must be a finite number.")
    if abs(amount) > MAX_UNITS:
        raise ValidationError(f"{field} must be at most {MAX_UNITS:,}.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError(f"{field} may have at most two decimal places.")
    return amount


def parse_amount(value, field="Amount") -> int:
    """Parse a strictly positive decimal amount into minor units."""
    amount = _decimal(value, field)
    if amount <= 0:
        raise ValidationError(f"{field} must be greater than zero.")
    return int(amount * 100)


def parse_nonnegative(value, field="Amount") -> int:
    amount = _decimal(value, field)
    if amount < 0:
        raise ValidationError(f"{field} cannot be negative.")
    return int(amount * 100)


def minor_value(raw: dict, field: str, label=None, allow_zero=False, default=None) -> int:
    """Read ``<field>_minor`` (exact integer) or ``<field>`` (decimal units).

    Supplying both is allowed only when they agree, so retries and imports
    are deterministic and a float conversion can never silently change money.
    """
    label = label or field
    minor_key = f"{field}_minor"
    has_minor = raw.get(minor_key) not in (None, "")
    has_units = raw.get(field) not in (None, "")
    if not has_minor and not has_units:
        if default is not None:
            return default
        raise ValidationError(f"{label} is required.")
    result = None
    if has_minor:
        value = raw[minor_key]
        if isinstance(value, str) and re.fullmatch(r"\d{1,12}", value.strip()):
            value = int(value.strip())
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValidationError(f"{minor_key} must be an integer number of minor units.")
        if value < 0 or value > MAX_AMOUNT_MINOR or (value == 0 and not allow_zero):
            raise ValidationError(f"{minor_key} is outside the supported range.")
        result = value
    if has_units:
        parsed = parse_nonnegative(raw[field], label) if allow_zero else parse_amount(raw[field], label)
        if result is not None and parsed != result:
            raise ValidationError(f"{field} and {minor_key} do not agree.")
        result = parsed
    return result


def clean_text(value):
    """NFKC-normalise and strip invisible format characters (zero-width, bidi, tag).

    Returns (clean_text, removed_count).  Hidden characters are a known way to
    smuggle instructions past a human reviewer, so removals are flagged.
    """
    normalised = unicodedata.normalize("NFKC", value)
    kept = [c for c in normalised if unicodedata.category(c) != "Cf"]
    return "".join(kept), len(normalised) - len(kept)


def text_value(raw, key, required=True, limit=300, label=None, default="", hidden=None):
    value = raw.get(key, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ValidationError(f"{label or key} must be text.")
    value, removed = clean_text(value)
    if hidden is not None and removed:
        hidden.append(key)
    value = value.strip()
    if required and not value:
        raise ValidationError(f"{label or key} is required.")
    if len(value) > limit or any(ord(c) < 32 and c != "\t" for c in value):
        raise ValidationError(f"{label or key} must be printable text of at most {limit} characters.")
    return value


def bool_value(raw, key, default=False):
    value = raw.get(key, default)
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in ("true", "1", "yes", "y"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "0", "no", "n"):
        return False
    raise ValidationError(f"{key} must be true or false.")


def int_value(raw, key, default, low, high, label=None):
    value = raw.get(key, default)
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,9}", value.strip()):
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValidationError(f"{label or key} must be a whole number from {low} to {high}.")
    return value


def _scope(raw, business_id):
    identifier = validate_business_id(business_id or raw.get("business_id", ""))
    if raw.get("business_id") not in (None, "", identifier):
        raise ValidationError("Record business_id does not match the requested business.")
    return identifier


# ---------------------------------------------------------------------------
# Untrusted-text screening.  Free text from records is data, never an
# instruction.  These flags make that boundary visible and testable; they do
# not decide anything on their own.

from .screening import INJECTION_PATTERNS, PAYMENT_REVIEW_FLAGS, scan_text


PAYROLL_WORDS = ("payroll", "salary", "salaries", "wage", "wages", "staff pay", "staff cost", "bonus")


def is_payroll_text(*values) -> bool:
    text = " ".join(str(value or "") for value in values).casefold()
    return any(word in text for word in PAYROLL_WORDS)


# ---------------------------------------------------------------------------
# Business, policy and records


def validate_business(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Business must be an object.")
    identifier = validate_business_id(raw.get("business_id", raw.get("id", "")))
    currency = normalize_currency(raw.get("currency", "BDT"))
    opening = minor_value(raw, "opening_cash", "Opening cash", allow_zero=True)
    opening_date = valid_date(raw.get("opening_date", "2026-10-01"), "opening_date")
    target = valid_date(raw.get("default_target_date", add_days(opening_date, 30)), "default_target_date")
    if target < opening_date:
        raise ValidationError("default_target_date cannot be before opening_date.")
    if days_between(opening_date, target) > MAX_PROJECTION_DAYS:
        raise ValidationError("default_target_date is beyond the 366-day horizon.")
    country = raw.get("country") or ""
    if country and (not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country)):
        raise ValidationError("country must be a two-letter ISO code.")
    synthetic = raw.get("synthetic", True)
    if not isinstance(synthetic, bool):
        raise ValidationError("synthetic must be true or false.")
    return {"business_id": identifier, "name": text_value(raw, "name", limit=120),
            "currency": currency, "opening_cash_minor": opening, "opening_date": opening_date,
            "default_target_date": target, "country": country,
            "sector": text_value(raw, "sector", required=False, limit=80),
            "synthetic": synthetic}


def validate_policy(raw: dict, business_id: str, currency: str) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Policy must be an object.")
    identifier = _scope(raw, business_id)
    if raw.get("currency") not in (None, ""):
        normalize_currency(raw.get("currency"), currency)
    reserve = minor_value(raw, "reserve_floor", "Reserve floor", allow_zero=True)
    limit = minor_value(raw, "action_limit", "Action limit", allow_zero=True)
    daily_cap = minor_value(raw, "daily_cap", "Daily cap", allow_zero=True, default=limit * 2)
    dual = minor_value(raw, "dual_approval_threshold", "Dual-approval threshold", allow_zero=True, default=limit)
    if daily_cap < limit:
        raise ValidationError("Daily cap must be at least the per-action limit.")
    if raw.get("payroll_priority", True) is not True:
        raise ValidationError("Payroll protection cannot be disabled.")
    autonomy = raw.get("autonomy_level", "propose")
    if autonomy not in AUTONOMY_LEVELS:
        raise ValidationError("autonomy_level must be advise, propose or delegate.")
    version = raw.get("version", "policy-v1")
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", version):
        raise ValidationError("Policy version is invalid.")
    return {"business_id": identifier, "currency": currency,
            "reserve_floor_minor": reserve, "action_limit_minor": limit,
            "daily_cap_minor": daily_cap, "dual_approval_threshold_minor": dual,
            "max_deferral_days": int_value(raw, "max_deferral_days", 14, 1, 60, "Maximum deferral days"),
            "max_discount_bps": int_value(raw, "max_discount_bps", 300, 0, 1000, "Maximum discount (basis points)"),
            "lookahead_days": int_value(raw, "lookahead_days", 14, 0, 60, "Look-ahead days"),
            "autonomy_level": autonomy, "agent_paused": bool_value(raw, "agent_paused", False),
            "payroll_priority": True, "version": version}


def validate_transaction(raw: dict, business_id: str, currency: str) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Each transaction must be an object.")
    identifier = _scope(raw, business_id)
    record_id = raw.get("id") or raw.get("transaction_id")
    if record_id not in (None, ""):
        validate_record_id(record_id, "Transaction id")
    kind = str(raw.get("type", "")).strip().lower()
    if kind not in TRANSACTION_TYPES:
        raise ValidationError("Transaction type must be income or expense.")
    hidden = []
    description = text_value(raw, "description", limit=300, hidden=hidden)
    category = "Income" if kind == "income" else text_value(raw, "category", required=False, limit=80) or "Other"
    return {"id": record_id or None, "business_id": identifier,
            "date": valid_date(raw.get("date", ""), "Transaction date"),
            "description": description, "type": kind,
            "amount_minor": minor_value(raw, "amount", "Transaction amount"),
            "currency": normalize_currency(raw.get("currency"), currency), "category": category,
            "risk_flags": scan_text(description) + (["hidden_characters"] if hidden else [])}


def validate_invoice(raw: dict, business_id: str, currency: str) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Each invoice must be an object.")
    identifier = _scope(raw, business_id)
    invoice_id = validate_record_id(raw.get("id", raw.get("invoice_id")), "Invoice id")
    due = valid_date(raw.get("due_date", ""), "due_date")
    issue = valid_date(raw.get("issue_date") or raw.get("date") or due, "issue_date")
    expected = valid_date(raw.get("expected_collection_date") or due, "expected_collection_date")
    if due < issue:
        raise ValidationError("Invoice due_date cannot be before issue_date.")
    if expected < issue:
        raise ValidationError("expected_collection_date cannot be before issue_date.")
    status = str(raw.get("status") or "confirmed").strip().lower()
    if status not in INVOICE_STATUSES:
        raise ValidationError("Invoice status is invalid.")
    paid_date = raw.get("paid_date") or None
    if paid_date is not None:
        paid_date = valid_date(paid_date, "paid_date")
        if status not in SETTLED_INVOICE_STATUSES:
            raise ValidationError("paid_date is only allowed for paid or collected invoices.")
        if paid_date < issue:
            raise ValidationError("paid_date cannot be before issue_date.")
    hidden = []
    customer = text_value({"customer": raw.get("customer") or raw.get("counterparty") or "Customer"}, "customer", limit=160, hidden=hidden)
    description = text_value({"description": raw.get("description") or "Receivable"}, "description", limit=300, hidden=hidden)
    return {"id": invoice_id, "business_id": identifier, "customer": customer,
            "description": description, "issue_date": issue, "due_date": due,
            "expected_collection_date": expected, "status": status, "paid_date": paid_date,
            "amount_minor": minor_value(raw, "amount", "Invoice amount"),
            "currency": normalize_currency(raw.get("currency"), currency),
            "risk_flags": scan_text(customer, description) + (["hidden_characters"] if hidden else [])}


def validate_bill(raw: dict, business_id: str, currency: str) -> dict:
    if not isinstance(raw, dict):
        raise ValidationError("Each bill must be an object.")
    identifier = _scope(raw, business_id)
    bill_id = validate_record_id(raw.get("id", raw.get("bill_id")), "Bill id")
    due = valid_date(raw.get("due_date", ""), "due_date")
    status = str(raw.get("status") or "open").strip().lower()
    if status not in BILL_STATUSES:
        raise ValidationError("Bill status is invalid.")
    priority = str(raw.get("priority") or "normal").strip().lower()
    if priority not in BILL_PRIORITIES:
        raise ValidationError("Bill priority is invalid.")
    rescheduled = raw.get("rescheduled_date") or None
    if rescheduled is not None:
        rescheduled = valid_date(rescheduled, "rescheduled_date")
        if rescheduled <= due:
            raise ValidationError("rescheduled_date must be later than due_date.")
    if status == "rescheduled" and not rescheduled:
        raise ValidationError("Rescheduled bills require rescheduled_date.")
    if status != "rescheduled" and rescheduled:
        raise ValidationError("rescheduled_date requires status=rescheduled.")
    account = raw.get("payee_account") or None
    if account is not None and (not isinstance(account, str) or not ACCOUNT_RE.fullmatch(account.strip())):
        raise ValidationError("payee_account must be 4-40 letters, digits, spaces or dashes.")
    hidden = []
    payee = text_value({"payee": raw.get("payee") or raw.get("counterparty") or "Supplier"}, "payee", limit=160, hidden=hidden)
    description = text_value({"description": raw.get("description") or "Supplier bill"}, "description", limit=300, hidden=hidden)
    reschedule_allowed = bool_value(raw, "reschedule_allowed", False)
    if priority == "payroll" and reschedule_allowed:
        raise ValidationError("Payroll bills cannot be marked reschedulable.")
    if priority != "payroll" and is_payroll_text(payee, description):
        raise ValidationError("This bill looks like payroll (salary or wages). Set priority=payroll so it is never deferred.")
    return {"id": bill_id, "business_id": identifier, "payee": payee,
            "payee_account": account.strip() if account else None,
            "description": description, "due_date": due,
            "amount_minor": minor_value(raw, "amount", "Bill amount"),
            "currency": normalize_currency(raw.get("currency"), currency), "status": status,
            "priority": priority, "reschedule_allowed": reschedule_allowed,
            "rescheduled_date": rescheduled, "risk_flags": scan_text(payee, description) + (["hidden_characters"] if hidden else [])}


CSV_COLUMNS = ("record_type", "business_id", "id", "date", "description", "amount", "amount_minor", "type",
               "currency", "category", "due_date", "status", "customer", "payee", "payee_account",
               "issue_date", "expected_collection_date", "paid_date", "priority", "reschedule_allowed",
               "rescheduled_date", "risk_flags", "source")
IGNORED_CSV_COLUMNS = ("risk_flags", "source")  # written by Tideway's export; recomputed on import, never trusted


def _unguard(value):
    """Undo the apostrophe Tideway's export adds before =, +, - or @ so an exported file re-imports unchanged."""
    if isinstance(value, str) and value.startswith("'") and value[1:].lstrip()[:1] in ("=", "+", "-", "@"):
        return value[1:]
    return value


def parse_combined_csv(text: str, business_id: str, currency: str) -> dict:
    """Validate a transaction/invoice/bill CSV completely before persistence."""
    business_id = validate_business_id(business_id)
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1_500_000:
        raise ValidationError("CSV must be UTF-8 text and no larger than 1.5 MB.")
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")), strict=True)
        if not reader.fieldnames:
            raise ValidationError("CSV must contain a header row.")
        fields = [field.strip() if isinstance(field, str) else field for field in reader.fieldnames]
        if len(set(fields)) != len(fields):
            raise ValidationError("Duplicate CSV column names are not allowed.")
        unknown = sorted(set(fields) - set(CSV_COLUMNS))
        if unknown:
            raise ValidationError(f"Unknown CSV column(s): {', '.join(unknown)[:120]}.")
        if "record_type" not in fields:
            raise ValidationError("CSV requires a record_type column (transaction, invoice or bill).")
        reader.fieldnames = fields
        rows = {"transactions": [], "invoices": [], "bills": []}
        seen = set()
        for line, raw in enumerate(reader, 2):
            if line > 5001:
                raise ValidationError("Import at most 5,000 rows at a time.")
            if None in raw:
                raise ValidationError(f"Row {line}: too many columns.")
            raw = {key: _unguard(value) for key, value in raw.items() if key not in IGNORED_CSV_COLUMNS}
            kind = str(raw.get("record_type", "")).strip().lower()
            if kind not in ("transaction", "invoice", "bill"):
                raise ValidationError(f"Row {line}: record_type must be transaction, invoice or bill.")
            if not str(raw.get("currency") or "").strip():
                raise ValidationError(f"Row {line}: currency is required.")
            try:
                if kind == "transaction":
                    record = validate_transaction(raw, business_id, currency)
                    identity = (kind, record["id"] or f"{record['date']}|{record['description']}|{record['amount_minor']}")
                    if identity in seen and not record["id"]:
                        raise ValidationError(f"Row {line}: same date, description and amount as an earlier row and no id. "
                                              "If both are real, give each row a distinct id.")
                    rows["transactions"].append(record)
                elif kind == "invoice":
                    record = validate_invoice(raw, business_id, currency)
                    identity = (kind, record["id"])
                    rows["invoices"].append(record)
                else:
                    record = validate_bill(raw, business_id, currency)
                    identity = (kind, record["id"])
                    rows["bills"].append(record)
            except ValidationError as exc:
                raise ValidationError(f"Row {line}: {exc}") from None
            if identity in seen:
                raise ValidationError(f"Row {line}: duplicate {kind} id in the same file.")
            seen.add(identity)
        if not any(rows.values()):
            raise ValidationError("CSV does not contain any records.")
        return rows
    except csv.Error as exc:
        raise ValidationError(f"CSV could not be read: {exc}") from None


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def human_date(value, year=False) -> str:
    """'2026-10-31' -> '31 Oct' (or '31 Oct 2026')."""
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{parsed.day} {parsed.strftime('%b')}" + (f" {parsed.year}" if year else "")


def money_text(minor: int, currency: str) -> str:
    sign = "-" if minor < 0 else ""
    units, cents = divmod(abs(int(minor)), 100)
    return f"{sign}{currency} {units:,}" + (f".{cents:02d}" if cents else "")
