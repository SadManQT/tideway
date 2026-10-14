"""The conversational layer shared by the local agent and TideLM.

* Small talk (greetings, thanks, "what can you do?", "how are we doing?") in many languages is
  answered instantly from live data, without calling any model.
* Every answer comes with follow-up suggestions picked from the business's actual situation,
  so the next useful question is always one click away.
* Anything not understood gets a helpful answer with concrete examples, never a dead end.
"""
from __future__ import annotations

import re

from .domain import money_text
from .i18n import ask, day, t

_GREETING = re.compile(
    r"^(hi+|hey+|hello+|hiya|yo|good (morning|afternoon|evening|day)|greetings|howdy|salam|salaam|assalamu? ?alaikum|"
    r"as-?salamu alaykum|namaste|namaskar|adab|hola|buen(os|as) (d[ií]as|tardes|noches)|bonjour|salut|bonsoir|ol[aá]|"
    r"oi|bom dia|boa tarde|halo|hai|selamat (pagi|siang|sore|malam)|apa kabar|kemon (acho|achen)|ki khobor|kya haal|"
    r"你好|您好|嗨|早上好|晚上好|大家好|مرحبا|السلام عليكم)[\s!.,?]*(there|tideway|tidelm|bot|team)?[\s!.,?]*$", re.I)
_THANKS = re.compile(
    r"^(thanks?( you)?( so much| a lot)?|thx|ty|cheers|great,? thanks|ok(ay)? thanks|dhonnobad|dhanyabad|dhanyavaad|"
    r"shukriya|shukran|谢谢(你|您)?|多谢|gracias|merci( beaucoup)?|obrigad[oa]|terima kasih|makasih|شكرا)[\s!.,]*$", re.I)
_HELP = re.compile(
    r"^(help|menu|start|\?|what can you do\??|what do you do\??|how (do|can) (i|you) use (this|you)\??|who are you\??|"
    r"what are you\??|features|commands|ayuda|aide|bantuan|madad|ki korte paro\??|tumi ki korte paro\??|"
    r"你能做什么[？?]?|你是谁[？?]?|帮助|怎么用[？?]?)[\s!.]*$", re.I)
_STATUS = re.compile(
    r"^(how('s| is| are)? (my business|business|we|things|it) (doing|going|looking)\??|status|overview|summary|"
    r"brief( me)?|daily brief|what('s| is) (new|up|happening)\??|any (problems|issues|alerts)\??|"
    r"¿?c[oó]mo va (el negocio|todo)\??|[çc]a va( les affaires)?\??|bagaimana bisnis saya\??|business kemon cholche\??|"
    r"business kaisa chal raha hai\??|生意怎么样[？?]?|情况怎么样[？?]?)[\s!.]*$", re.I)


def classify(message):
    """'greeting' | 'thanks' | 'help' | 'status' | None, for short conversational messages only."""
    text = " ".join(str(message).strip().split())
    if len(text) > 60:
        return None
    for label, pattern in (("greeting", _GREETING), ("thanks", _THANKS), ("help", _HELP), ("status", _STATUS)):
        if pattern.match(text):
            return label
    return None


def situation(app, business_id, target_date):
    """The few facts a conversation needs, from the same analysis the dashboard uses."""
    analysis = app.analysis(business_id, target_date)
    business = analysis["snapshot"]["business"]
    profiles = analysis["derived"]["profiles"]["customers"]
    owing = sorted((item for item in profiles.values() if item["open_exposure_minor"]),
                   key=lambda item: -(item.get("tidepay_delay_days") or item["expected_delay_days"]))
    base, likely = analysis["projections"]["base"], analysis["projections"]["likely"]
    payroll = next((event for event in base["source_references"] if event.get("payroll")), None)
    return {"business": business, "currency": business["currency"], "weather": analysis["weather"],
            "warnings": analysis["warnings"], "simulation": analysis["simulation"],
            "first_breach": base["first_breach_date"], "likely_min": likely["minimum_cash_minor"],
            "likely_min_date": likely["minimum_cash_date"],
            "payroll": (-payroll["effect_minor"], payroll["date"]) if payroll else None,
            "slowest": owing[0]["customer"] if owing else None,
            "largest": max(owing, key=lambda i: i["open_exposure_minor"])["customer"] if owing else None,
            "blocked": len(analysis["derived"]["blocked"]),
            "plan": app.store.latest_plan(business_id, analysis["target_date"]), "target_date": analysis["target_date"]}


def suggestions(facts, topic=None, customer=None, exclude=(), lang="en"):
    """Up to three next questions: what naturally follows this answer, then what matters most right now."""
    codes = {item["code"] for item in facts["warnings"]}
    slow, big = facts["slowest"], facts["largest"]
    who = customer or slow
    q = lambda key, **values: ask(lang, key, **values)  # noqa: E731
    rescue = q("why") if facts["plan"] is not None else (q("rescue") if facts["simulation"]["futures_short_of_20"] > 0 else None)
    follow = {
        "payroll": [rescue, q("risk"), who and q("whatif", who=who, days=15)],
        "risk": [rescue, q("payroll") if "payroll_at_risk" in codes else q("forecast"), q("late")],
        "forecast": [q("risk"), rescue, q("late")],
        "customer": [who and q("whatif", who=who, days=15), who and q("credit", who=who), q("remind")],
        "credit": [who and q("habit", who=who), who and q("whatif", who=who, days=15), q("late")],
        "receivables": [q("remind"), q("network"), big and q("habit", who=big)],
        "whatif": [rescue, q("risk"), big and big != customer and q("whatif", who=big, days=10)],
        "plan": [q("why"), q("risk"), q("remind")],
        "security": [q("risk"), rescue, q("late")],
    }.get(topic, [])
    situational = [q("payroll") if "payroll_at_risk" in codes else None, rescue, q("blocked") if facts["blocked"] else None,
                   slow and q("whatif", who=slow, days=15), q("late"), q("risk")]
    seen, result = {item.casefold() for item in exclude}, []
    for item in follow + situational:
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result[:3]


def briefing(facts, name=None, lang="en"):
    sim, currency = facts["simulation"], facts["currency"]
    weather = t(lang, "weather")[facts["weather"]["level"]]
    lines = [t(lang, "today", business=facts["business"]["name"], weather=weather),
             t(lang, "breach_scheduled", date=day(lang, facts["first_breach"]), short=sim["futures_short_of_20"])
             if facts["first_breach"] else t(lang, "breach_sim", short=sim["futures_short_of_20"]),
             t(lang, "lowest", amount=money_text(facts["likely_min"], currency), date=day(lang, facts["likely_min_date"]))]
    if facts["payroll"]:
        lines.append(t(lang, "payroll_due", amount=money_text(facts["payroll"][0], currency), date=day(lang, facts["payroll"][1])))
    critical = [t(lang, f"w_{item['code']}") for item in facts["warnings"]
                if item["severity"] == "critical" and f"w_{item['code']}" in _WARNINGS]
    if critical:
        lines.append(t(lang, "attention", items=("；" if lang == "zh" else "; ").join(critical[:2])))
    if facts["blocked"]:
        lines.append(t(lang, "blocked", n=facts["blocked"]))
    if facts["plan"] and facts["plan"].get("bundles"):
        lines.append(t(lang, "plan_ready", amount=money_text(facts["plan"]["bundles"][0]["economic_cost_minor"], currency)))
    else:
        lines.append(t(lang, "ask_plan") if sim["futures_short_of_20"] > 0 else t(lang, "all_good"))
    hello = t(lang, "hello", name=name.split()[0]) if name else t(lang, "hello_anon")
    return hello + _join(lang, lines)


_WARNINGS = {"w_reserve_breach", "w_payroll_at_risk", "w_payee_account_changed", "w_lookalike_payee"}


def small_talk(kind, facts, name=None, lang="en"):
    if kind == "thanks":
        return t(lang, "thanks")
    if kind == "help":
        return t(lang, "help")
    return briefing(facts, name if kind == "greeting" else None, lang)


def not_understood(facts, lang="en"):
    return t(lang, "not_understood", business=facts["business"]["name"])


def out_of_scope(lang="en"):
    return t(lang, "out_of_scope")


def _join(lang, lines):
    return "".join(lines) if lang == "zh" else " ".join(lines)


def explain_choice(plan, currency, lang="en"):
    """Why the recommended bundle won: its risk and cost against each rejected option, in plain words."""
    if not plan:
        return t(lang, "no_plan")
    bundles = plan.get("bundles") or []
    if not bundles:
        return t(lang, "plan_none")
    best, target = bundles[0], round(plan.get("risk_target", 0.1) * 20)
    lines = [t(lang, "why_best", after=best["futures_short_of_20_after"], target=target,
               cost=money_text(best["economic_cost_minor"], currency))]
    for other in bundles[1:]:
        gap = other["economic_cost_minor"] - best["economic_cost_minor"]
        if other["futures_short_of_20_after"] is not None and other["futures_short_of_20_after"] > target:
            lines.append(t(lang, "why_risky", cost=money_text(other["economic_cost_minor"], currency),
                           after=other["futures_short_of_20_after"]))
        elif gap > 0:
            lines.append(t(lang, "why_costlier", gap=money_text(gap, currency), n=other["counterparties"]))
    short = [item for item in plan.get("why_not", []) if item["reason"].startswith("INSUFFICIENT_ALONE")]
    if short:
        item = min(short, key=lambda i: int(re.sub(r"\D", "", i["reason"]) or 0))
        amount = re.search(r"([A-Z]{3} [\d,.]+)", item["reason"])
        lines.append(t(lang, "why_alone", who=item["counterparty"], short=amount.group(1) if amount else ""))
    financing = [item for item in plan.get("financing", []) if item.get("feasible")]
    if financing:
        lines.append(t(lang, "why_finance", fee=money_text(min(i["economic_cost_minor"] for i in financing), currency)))
    return _join(lang, lines)


def plan_summary(plan, currency, lang="en"):
    """A proposal in the reader's language, built from the plan's own numbers."""
    basis = plan["basis_projection"]
    if not plan["action_needed"]:
        return t(lang, "plan_none")
    lines = [t(lang, "plan_gap", amount=money_text(basis["minimum_cash_minor"], currency), date=day(lang, basis["minimum_cash_date"]),
               short=money_text(basis["reserve_shortfall_minor"], currency))]
    bundles = plan.get("bundles") or []
    if bundles and bundles[0]["feasible"]:
        best = bundles[0]
        actions = []
        for action in best["actions"]:
            if action["type"] == "supplier_deferral":
                actions.append(t(lang, "act_defer", who=action["counterparty"], amount=money_text(action["amount_minor"], currency),
                                 from_=day(lang, action["from_date"]), to=day(lang, action["to_date"])))
            else:
                actions.append(t(lang, "act_early", who=action["counterparty"], pct=f"{action['discount_bps'] / 100:g}",
                                 amount=money_text(action["face_minor"], currency), to=day(lang, action["to_date"])))
        lines.append(t(lang, "plan_recommend", actions="；".join(actions) if lang == "zh" else "; ".join(actions),
                       cost=money_text(best["economic_cost_minor"], currency), n=best["counterparties"],
                       after=best["futures_short_of_20_after"]))
    else:
        lines.append(t(lang, "plan_nosafe", short=money_text(bundles[0]["remaining_shortfall_minor"] if bundles
                                                             else basis["reserve_shortfall_minor"], currency)))
    lines.append(t(lang, "plan_wait"))
    return _join(lang, lines)


def whatif_text(projection, baseline, currency, lang="en", label=None):
    worse = baseline["minimum_cash_minor"] - projection["minimum_cash_minor"]
    change = (t(lang, "worse", amount=money_text(worse, currency), base=money_text(baseline["minimum_cash_minor"], currency))
              if worse > 0 else t(lang, "same") if worse == 0 else t(lang, "better", amount=money_text(-worse, currency)))
    text = t(lang, "whatif", amount=money_text(projection["minimum_cash_minor"], currency),
             date=day(lang, projection["minimum_cash_date"]), change=change,
             short=money_text(projection["reserve_shortfall_minor"], currency))
    return text.replace("With that change", label, 1) if label and lang == "en" else text
