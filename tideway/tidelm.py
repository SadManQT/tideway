"""TideLM at runtime: Tideway's own fine-tuned small language model, running locally with MLX.

Two skills, both trained on Tideway's own data (tideway/ml/tidelm_data.py):
  * plan    - turn an owner's message (English, Banglish, typos) into a typed tool-call plan;
  * extract - turn pasted SMS / WhatsApp / bank text into draft ledger records and flag injection.

The model never touches money or records directly.  Plans go through copilot.validate_plan and
copilot.run_plan (read / propose tools only, names resolved against the ledger), and replies are
written by code from tool output, so every number comes from Tideway, not from the model.
Extracted records are drafts until a person confirms them.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

from . import copilot
from .domain import (SecurityError, ValidationError, canonical_json, scan_text, validate_bill, validate_invoice,
                     validate_transaction)
from .ml.tidelm_data import EXTRACT_SYSTEM, PLAN_SYSTEM

ROOT = Path(__file__).resolve().parent.parent
BASE_MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
ADAPTER = ROOT / "models" / "tidelm-adapter"
MAX_INPUT = 2000
PLANNER_ROLES = ("owner", "accountant")
PROPOSING_TOOLS = ("propose_plan", "draft_reminders")


class TideLMUnavailable(RuntimeError):
    """MLX or the trained adapter is missing; the caller must say so, not substitute something else."""


def parse_json(text):
    """The first JSON object in the model's output, or None."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        value = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class TideLM:
    def __init__(self, adapter=ADAPTER, generator=None):
        """``generator(system, user) -> str`` may be injected for tests; otherwise MLX is loaded lazily."""
        self.adapter = Path(adapter)
        self._generator = generator
        self._model = self._tokenizer = None
        self._lock = threading.Lock()  # MLX generation is not thread-safe; one request at a time

    # ---- model ---------------------------------------------------------------------

    def status(self):
        if self._generator is not None:
            return {"available": True, "loaded": True, "model": "injected", "adapter": None}
        try:
            import mlx_lm  # noqa: F401
            mlx = True
        except ImportError:
            mlx = False
        ready = mlx and (self.adapter / "adapters.safetensors").exists()
        return {"available": ready, "loaded": self._model is not None, "model": BASE_MODEL,
                "adapter": str(self.adapter.relative_to(ROOT)) if self.adapter.is_relative_to(ROOT) else str(self.adapter),
                "reason": None if ready else ("Install mlx-lm (Apple Silicon)." if not mlx else
                                              "Train the adapter: python3 -m mlx_lm lora --config tideway/ml/tidelm_lora.yaml")}

    def _generate(self, system, user, max_tokens=400):
        if self._generator is not None:
            return self._generator(system, user)
        status = self.status()
        if not status["available"]:
            raise TideLMUnavailable(f"TideLM is not available: {status['reason']}")
        with self._lock:
            if self._model is None:
                from mlx_lm import load
                self._model, self._tokenizer = load(BASE_MODEL, adapter_path=str(self.adapter))
            from mlx_lm import generate
            prompt = self._tokenizer.apply_chat_template([{"role": "system", "content": system},
                                                          {"role": "user", "content": user}],
                                                         add_generation_prompt=True, tokenize=False)
            return generate(self._model, self._tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)

    # ---- skill 1: plan and answer ---------------------------------------------------

    def ask(self, app, business_id, target_date, message, role, actor="agent:tidelm"):
        if not isinstance(message, str) or not message.strip() or len(message) > MAX_INPUT:
            raise ValidationError(f"Message must contain 1-{MAX_INPUT:,} characters.")
        started = time.monotonic()
        raw = self._generate(PLAN_SYSTEM, message.strip())
        plan = parse_json(raw)
        currency = app.store.get_business(business_id)["currency"]
        trace = {"mode": "tidelm", "input_sha256": hashlib.sha256(message.encode()).hexdigest(),
                 "plan": plan, "elapsed_ms": None}
        try:
            if plan is None:
                raise ValidationError("TideLM did not return a valid plan.")
            copilot.validate_plan(plan)
            if role not in PLANNER_ROLES and any(call["tool"] in PROPOSING_TOOLS for call in plan["calls"]):
                text = "Viewers can read forecasts and reports, but only an owner or accountant can ask for plans or reminders."
                results = []
            else:
                results = copilot.run_plan(app, business_id, target_date, plan, actor)
                text = copilot.reply_from_results(results, currency)
            permission = "agent_read"
        except ValidationError as exc:  # a refused or unparseable plan is answered, never guessed
            text, results, permission = f"I couldn't do that safely: {exc}", [], "denied"
            if isinstance(exc, SecurityError):  # the model asked for a forbidden tool: counts toward the breaker
                app.store.reject(business_id, "agent.tool_rejected", actor, exc, {"plan": plan}, security_relevant=True)
        trace["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        app.store.audit(business_id, "agent.answer", actor, permission,
                        {**trace, "tools": [call.get("tool") for call in (plan or {}).get("calls", []) if isinstance(call, dict)],
                         "output_sha256": hashlib.sha256(text.encode()).hexdigest()})
        return {"text": text, "mode": "tidelm", "plan": plan, "results": results, "elapsed_ms": trace["elapsed_ms"]}

    # ---- skill 2: zero-entry inbox --------------------------------------------------

    def extract(self, app, business_id, text, actor="agent:tidelm"):
        """Draft records from pasted text.  Nothing is saved; a person confirms with ``confirm``."""
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_INPUT:
            raise ValidationError(f"Pasted text must contain 1-{MAX_INPUT:,} characters.")
        business = app.store.get_business(business_id)
        output = parse_json(self._generate(EXTRACT_SYSTEM, text.strip(), max_tokens=600))
        if output is None or not isinstance(output.get("records"), list):
            raise ValidationError("TideLM could not read records from that text.")
        flags = scan_text(text)  # deterministic check alongside the model's own judgement
        drafts = []
        for index, row in enumerate(output["records"][:20]):
            if isinstance(row, dict):
                drafts.append(_draft(row, index, text, business))
        result = {"drafts": drafts, "suspicious": bool(output.get("suspicious")) or bool(flags), "risk_flags": flags,
                  "note": "Drafts only. Check each one; nothing is saved until you confirm."}
        app.store.audit(business_id, "inbox.extract", actor, "agent_read",
                        {"input_sha256": hashlib.sha256(text.encode()).hexdigest(), "drafts": len(drafts),
                         "suspicious": result["suspicious"], "risk_flags": flags})
        return result


def _draft(row, index, text, business):
    """Map one extracted record to the ledger's raw import shape (validated again on confirm)."""
    kind = row.get("record_type") if row.get("record_type") in ("invoice", "bill", "transaction") else "transaction"
    reference = row.get("reference") if isinstance(row.get("reference"), str) else None
    digest = hashlib.sha256(canonical_json([text, index, row]).encode()).hexdigest()[:12]
    counterparty = str(row.get("counterparty") or "").strip()[:160]
    common = {"amount": row.get("amount"), "currency": row.get("currency") or business["currency"]}
    if kind == "invoice":
        raw = {**common, "record_type": "invoice", "id": f"inbox-{digest}", "customer": counterparty,
               "issue_date": row.get("date") or row.get("due_date"), "due_date": row.get("due_date") or row.get("date"),
               "description": f"Invoice {reference}" if reference else "Invoice from inbox"}
    elif kind == "bill":
        raw = {**common, "record_type": "bill", "id": f"inbox-{digest}", "payee": counterparty,
               "due_date": row.get("due_date") or row.get("date"),
               "description": f"Bill {reference}" if reference else "Bill from inbox"}
    else:
        raw = {**common, "record_type": "transaction", "id": f"inbox-{digest}", "date": row.get("date") or row.get("due_date"),
               "type": "income" if row.get("direction") == "in" else "expense",
               "description": (f"{counterparty} {reference or ''}".strip() or "Inbox transaction")[:300], "category": "Other"}
    try:
        _validate(raw, business)
        problem = None
    except ValidationError as exc:
        problem = str(exc)
    return {"record": raw, "ready": problem is None, "problem": problem}


def _validate(raw, business):
    record = {key: value for key, value in raw.items() if key != "record_type"}
    validator = {"invoice": validate_invoice, "bill": validate_bill, "transaction": validate_transaction}[raw["record_type"]]
    return validator(record, business["id"], business["currency"])


def confirm(app, business_id, records, actor):
    """Save drafts a person reviewed (and may have edited).  Every field is validated again."""
    if not isinstance(records, list) or not 0 < len(records) <= 20:
        raise ValidationError("Confirm 1-20 records at a time.")
    business = app.store.get_business(business_id)
    parsed = {"transactions": [], "invoices": [], "bills": []}
    for raw in records:
        if not isinstance(raw, dict) or raw.get("record_type") not in ("invoice", "bill", "transaction"):
            raise ValidationError("Each record needs record_type invoice, bill or transaction.")
        try:
            record = _validate(raw, business)
        except ValidationError as exc:
            raise ValidationError(f"{raw.get('id', 'record')}: {exc}") from None
        parsed[{"invoice": "invoices", "bill": "bills", "transaction": "transactions"}[raw["record_type"]]].append(record)
    return app.store.import_records(business_id, parsed, actor, "inbox")
