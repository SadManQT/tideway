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

from . import conversation, copilot, i18n
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
        self._caches = {}

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

    def _load(self):
        if self._model is None:
            from mlx_lm import load
            self._model, self._tokenizer = load(BASE_MODEL, adapter_path=str(self.adapter))

    def _prefix_cache(self, system):
        """KV cache of the chat template up to where the user's text begins, computed once per skill.

        Every request then processes only the user's own tokens instead of the ~300-token system
        prompt again.  Returns (cache, prefix_tokens)."""
        if system not in self._caches:
            import mlx.core as mx
            from mlx_lm.models.cache import make_prompt_cache
            marker = "\u2063TIDEWAY_USER\u2063"
            template = self._tokenizer.apply_chat_template(
                [{"role": "system", "content": system}, {"role": "user", "content": marker}],
                add_generation_prompt=True, tokenize=False)
            prefix = self._tokenizer.encode(template.split(marker)[0], add_special_tokens=False)
            cache = make_prompt_cache(self._model)
            self._model(mx.array(prefix)[None], cache=cache)
            mx.eval([entry.state for entry in cache])
            self._caches[system] = (cache, prefix)
        return self._caches[system]

    def _generate(self, system, user, max_tokens=400):
        if self._generator is not None:
            return self._generator(system, user)
        status = self.status()
        if not status["available"]:
            raise TideLMUnavailable(f"TideLM is not available: {status['reason']}")
        with self._lock:
            self._load()
            from mlx_lm import generate
            from mlx_lm.models.cache import trim_prompt_cache
            prompt = self._tokenizer.apply_chat_template([{"role": "system", "content": system},
                                                          {"role": "user", "content": user}],
                                                         add_generation_prompt=True, tokenize=False)
            tokens = self._tokenizer.encode(prompt, add_special_tokens=False)
            cache, prefix = self._prefix_cache(system)
            if tokens[:len(prefix)] != prefix:  # tokenisation differs at the boundary: correctness first, no cache
                return generate(self._model, self._tokenizer, prompt=tokens, max_tokens=max_tokens, verbose=False)
            try:
                return generate(self._model, self._tokenizer, prompt=tokens[len(prefix):], max_tokens=max_tokens,
                                verbose=False, prompt_cache=cache)
            finally:  # roll the shared cache back to the system prompt for the next request
                trim_prompt_cache(cache, cache[0].offset - len(prefix))

    def warm(self):
        """Load the model and both prompt caches ahead of the first question (run in a background thread)."""
        if self._generator is not None or not self.status()["available"]:
            return False
        with self._lock:
            self._load()
            for system in (PLAN_SYSTEM, EXTRACT_SYSTEM):
                self._prefix_cache(system)
        return True

    # ---- skill 1: plan and answer ---------------------------------------------------

    def ask(self, app, business_id, target_date, message, role, actor="agent:tidelm", name=None):
        if not isinstance(message, str) or not message.strip() or len(message) > MAX_INPUT:
            raise ValidationError(f"Message must contain 1-{MAX_INPUT:,} characters.")
        started = time.monotonic()
        lang = i18n.detect(message)  # answer in the language of the question
        small = conversation.classify(message)
        if small:  # greetings, thanks, help, status: answered instantly from live data, no model call
            facts = conversation.situation(app, business_id, target_date)
            return {"text": conversation.small_talk(small, facts, name, lang), "mode": "tidelm", "plan": None, "results": [],
                    "routed": "small_talk", "lang": lang, "suggestions": conversation.suggestions(facts, lang=lang),
                    "elapsed_ms": int((time.monotonic() - started) * 1000)}
        raw = self._generate(PLAN_SYSTEM, message.strip())
        plan = parse_json(raw)
        currency = app.store.get_business(business_id)["currency"]
        trace = {"mode": "tidelm", "input_sha256": hashlib.sha256(message.encode()).hexdigest(),
                 "plan": plan, "elapsed_ms": None}
        try:
            if plan is None:
                raise ValueError("unparseable")
            copilot.validate_plan(plan)
            if role not in PLANNER_ROLES and any(call["tool"] in PROPOSING_TOOLS for call in plan["calls"]):
                text = i18n.t(lang, "viewer")
                results = []
            else:
                results = copilot.run_plan(app, business_id, target_date, plan, actor, lang)
                text = copilot.reply_from_results(results, currency, lang)
            permission = "agent_read"
        except ValueError as exc:  # a refused or unparseable plan is answered, never guessed
            if not isinstance(exc, ValidationError):
                exc = None
            results, permission = [], "denied"
            text = (i18n.t(lang, "unsafe", reason=exc) if exc else
                    conversation.not_understood(conversation.situation(app, business_id, target_date), lang))
            if isinstance(exc, SecurityError):  # the model asked for a forbidden tool: counts toward the breaker
                app.store.reject(business_id, "agent.tool_rejected", actor, exc, {"plan": plan}, security_relevant=True)
        trace["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        app.store.audit(business_id, "agent.answer", actor, permission,
                        {**trace, "tools": [call.get("tool") for call in (plan or {}).get("calls", []) if isinstance(call, dict)],
                         "output_sha256": hashlib.sha256(text.encode()).hexdigest()})
        topic, focus = _topic(plan, results)
        follow = conversation.suggestions(conversation.situation(app, business_id, target_date), topic, focus,
                                          exclude=(message.strip(),), lang=lang)
        return {"text": text, "mode": "tidelm", "plan": plan, "results": results, "suggestions": follow, "lang": lang,
                "elapsed_ms": trace["elapsed_ms"]}

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


TOPICS = {"project_cash": "forecast", "simulate_risk": "risk", "what_if": "whatif", "propose_plan": "plan",
          "explain_plan": "plan", "credit_check": "credit", "draft_reminders": "receivables", "bank_pack": "risk"}


def _topic(plan, results):
    """The conversation topic and customer in focus, used to pick follow-up suggestions."""
    calls = [call for call in (plan or {}).get("calls", []) if isinstance(call, dict)]
    if not calls or not results:
        return None, None
    tool, args = calls[0].get("tool"), calls[0].get("args") or {}
    if (plan or {}).get("intent") == "payroll_check":
        return "payroll", None
    if tool == "customer_report":
        return ("customer", args.get("customer")) if args.get("customer") else ("receivables", None)
    focus = args.get("customer") or next(iter((args.get("customer_delays") or {})), None)
    return TOPICS.get(tool), focus if isinstance(focus, str) else None


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
