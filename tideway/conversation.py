"""The conversational layer shared by the local agent and TideLM.

* Small talk (greetings, thanks, "what can you do?", "how are we doing?") in many languages is
  answered instantly from live data, without calling any model.
* Every answer comes with follow-up suggestions picked from the business's actual situation,
  so the next useful question is always one click away.
* Anything not understood gets a helpful answer with concrete examples, never a dead end.
"""
from __future__ import annotations

import re

from .domain import human_date, money_text

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


CAPABILITIES = ("I can tell you whether payroll is safe, how likely you are to run short, which customers pay late and "
                "what TidePay expects from them, run a what-if (\"what if a customer pays 15 days late?\"), check if a "
                "customer is safe to sell to on credit, draft payment reminders, build a rescue plan for a person to "
                "approve, and prepare a bank-ready pack. I never approve or move money myself.")


def situation(app, business_id, target_date):
    """The few facts a conversation needs, from the same analysis the dashboard uses."""
    analysis = app.analysis(business_id, target_date)
    business = analysis["snapshot"]["business"]
    profiles = analysis["derived"]["profiles"]["customers"]
    owing = sorted((item for item in profiles.values() if item["open_exposure_minor"]),
                   key=lambda item: -(item.get("tidepay_delay_days") or item["expected_delay_days"]))
    blocked = analysis["derived"]["blocked"]
    plan = app.store.latest_plan(business_id, analysis["target_date"])
    return {"business": business, "currency": business["currency"], "brief": analysis["brief"],
            "weather": analysis["weather"], "warnings": analysis["warnings"], "simulation": analysis["simulation"],
            "slowest": owing[0]["customer"] if owing else None, "largest": max(owing, key=lambda i: i["open_exposure_minor"])["customer"] if owing else None,
            "blocked": len(blocked), "plan": plan, "target_date": analysis["target_date"]}


def suggestions(facts, topic=None, customer=None, exclude=()):
    """Up to three next questions: what naturally follows this answer, then what matters most right now."""
    codes = {item["code"] for item in facts["warnings"]}
    slow, big = facts["slowest"], facts["largest"]
    who = customer or slow
    rescue = "Why this plan?" if facts["plan"] is not None else (
        "Find me a rescue plan" if facts["simulation"]["futures_short_of_20"] > 0 else None)
    follow = {
        "payroll": [rescue, "How risky is this month?", who and f"What if {who} pays 15 days late?"],
        "risk": [rescue, "Can I pay salaries this month?" if "payroll_at_risk" in codes else "Show the cash forecast",
                 "Which customers pay late?"],
        "forecast": ["How risky is this month?", rescue, "Which customers pay late?"],
        "customer": [who and f"What if {who} pays 15 days late?", who and f"Should I give {who} 30 days credit on 20,000?",
                     "Remind everyone who owes me"],
        "credit": [who and f"How does {who} usually pay?", who and f"What if {who} pays 15 days late?", "Which customers pay late?"],
        "receivables": ["Remind everyone who owes me", big and f"How does {big} usually pay?", slow and f"What if {slow} pays 15 days late?"],
        "whatif": [rescue, "How risky is this month?", big and big != customer and f"What if {big} pays 10 days late?"],
        "plan": ["Why this plan?", "How risky is this month?", "Remind everyone who owes me"],
        "security": ["How risky is this month?", rescue, "Which customers pay late?"],
    }.get(topic, [])
    situational = ["Can I pay salaries this month?" if "payroll_at_risk" in codes else None, rescue,
                   "Which bills are blocked and why?" if facts["blocked"] else None,
                   slow and f"What if {slow} pays 15 days late?", "Which customers pay late?", "How risky is this month?"]
    seen, result = {item.casefold() for item in exclude}, []
    for item in follow + situational:
        if item and item.casefold() not in seen:
            seen.add(item.casefold())
            result.append(item)
    return result[:3]


def briefing(facts, name=None):
    weather, sim, currency = facts["weather"], facts["simulation"], facts["currency"]
    lines = [f"{facts['business']['name']} today: {weather['label']}. {facts['brief']['headline']}.", facts["brief"]["detail"]]
    critical = [item for item in facts["warnings"] if item["severity"] == "critical"]
    if critical:
        lines.append("Needs attention: " + "; ".join(item["title"] for item in critical[:2]) + ".")
    if facts["blocked"]:
        lines.append(f"{facts['blocked']} bill(s) are blocked for possible payment fraud.")
    if facts["plan"] and facts["plan"].get("bundles"):
        best = facts["plan"]["bundles"][0]
        lines.append(f"A rescue plan is ready (cost {money_text(best['economic_cost_minor'], currency)}); "
                     "it waits for a person to approve it.")
    elif sim["futures_short_of_20"] > 0:
        lines.append("Ask me for a rescue plan.")
    else:
        lines.append("No action is needed right now.")
    hello = f"Hi {name.split()[0]}! " if name else "Hi! "
    return hello + " ".join(lines)


def small_talk(kind, facts, name=None):
    if kind == "thanks":
        return "You're welcome. " + ("Anything else? " if facts else "")
    if kind == "help":
        return CAPABILITIES + " Try one of the suggestions below."
    if kind == "status":
        return briefing(facts, None)
    return briefing(facts, name)


def not_understood(facts):
    return ("I'm not sure what you mean. I'm Tideway's cash-flow copilot for "
            f"{facts['business']['name']}: ask about cash, payroll, customers, risk or a rescue plan, in your own words "
            "and language. For example:")


def out_of_scope():
    return ("That's outside what I do; I only work on this business's cash flow. I can answer questions about payroll, "
            "risk, customers, what-ifs, credit checks, reminders and rescue plans.")



def explain_choice(plan, currency):
    """Why the recommended bundle won: its risk and cost against each rejected option, in plain words."""
    if not plan:
        return "There is no current proposal yet. Ask me for a rescue plan first."
    bundles = plan.get("bundles") or []
    if not bundles:
        return plan.get("explanation") or "No proposal could hold the reserve floor."
    best, target = bundles[0], round(plan.get("risk_target", 0.1) * 20)
    lines = [f"I recommend this bundle because it holds the reserve floor every day with payroll funded, and only "
             f"{best['futures_short_of_20_after']} of 20 simulated futures still fall short (my bar is {target} or fewer), "
             f"at an economic cost of {money_text(best['economic_cost_minor'], currency)}."]
    for other in bundles[1:]:
        cost_gap = other["economic_cost_minor"] - best["economic_cost_minor"]
        if other["futures_short_of_20_after"] is not None and other["futures_short_of_20_after"] > target:
            lines.append(f"A {'cheaper' if cost_gap < 0 else 'different'} option ({money_text(other['economic_cost_minor'], currency)}) "
                         f"leaves {other['futures_short_of_20_after']} of 20 futures short: too risky.")
        else:
            lines.append(f"Another safe option costs {money_text(abs(cost_gap), currency)} "
                         f"{'more' if cost_gap > 0 else 'less'} and asks {other['counterparties']} counterparties.")
    short = [item for item in plan.get("why_not", []) if item["reason"].startswith("INSUFFICIENT_ALONE")]
    if short:
        item = min(short, key=lambda i: int(re.sub(r"\D", "", i["reason"]) or 0))
        lines.append(f"No single action is enough: for example, the best request to {item['counterparty']} alone "
                     f"{item['reason'].split(': ', 1)[-1].replace('still', 'still leaves you')}")
    financing = [item for item in plan.get("financing", []) if item.get("feasible")]
    if financing:
        cheapest = min(financing, key=lambda item: item["economic_cost_minor"])
        lines.append(f"The cheapest financing would cost {money_text(cheapest['economic_cost_minor'], currency)} in fees "
                     "(illustrative mock offer), so it is kept as a fallback.")
    return " ".join(lines)


def whatif_text(label, projection, baseline, currency):
    worse = baseline["minimum_cash_minor"] - projection["minimum_cash_minor"]
    change = (f"{money_text(worse, currency)} worse than today's likely low of {money_text(baseline['minimum_cash_minor'], currency)}"
              if worse > 0 else "no worse than today's likely low" if worse == 0 else
              f"{money_text(-worse, currency)} better than today's likely low")
    return (f"{label}, the lowest likely cash is {money_text(projection['minimum_cash_minor'], currency)} on "
            f"{human_date(projection['minimum_cash_date'])}: {change}. Reserve shortfall "
            f"{money_text(projection['reserve_shortfall_minor'], currency)}. Nothing was saved.")
