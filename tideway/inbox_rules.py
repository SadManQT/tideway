"""Rule-based Inbox extraction: the fallback when TideLM is not installed.

Reads the alert formats Tideway documents (bank SMS, card alerts, M-Pesa, UPI, WeChat Pay,
Alipay, PayNow, DuitNow, GCash, Pix, SEPA, Faster Payments, Wise, bKash, invoice and bill
notices, and short chat promises such as "Nila Traders will pay 50,000 next Friday") with
regular expressions only.  It returns the same JSON shape TideLM's extractor returns, so the
records go through the same draft builder, validators, currency check and screening.

It is deliberately simple and says so: every draft is labelled as rule-based and must be
checked by a person.  Nothing here saves a record, and message text never gains authority.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from .domain import CURRENCIES

_MONTHS = {name: number for number, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_MONTH_RE = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
             r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?![a-z])")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# Currency symbols and words -> ISO codes; an ambiguous symbol prefers the business's own currency.
_SYMBOLS = (
    (r"R\$", ("BRL",)), (r"S\$", ("SGD",)), (r"HK\$", ("HKD",)), (r"A\$", ("AUD",)), (r"C\$", ("CAD",)),
    (r"NZ\$", ("NZD",)), (r"US\$", ("USD",)), (r"\$", ("USD", "SGD", "AUD", "CAD", "HKD", "NZD", "MXN")),
    (r"£", ("GBP",)), (r"€", ("EUR",)), (r"₹", ("INR",)), (r"৳", ("BDT",)), (r"₱", ("PHP",)), (r"₦", ("NGN",)),
    (r"[¥￥]", ("CNY",)), (r"(?<![A-Za-z])K[Ss]h\.?", ("KES",)),
    (r"(?<![A-Za-z])(?:Rs\.?|rs\.?|INR|[Rr]upees?)", ("INR", "PKR", "LKR", "NPR")),
    (r"(?<![A-Za-z])(?:Tk\.?|tk\.?|[Tt]aka)(?![a-z])", ("BDT",)), (r"(?<![A-Za-z])Rp\.?", ("IDR",)),
    (r"(?<![A-Za-z])RM", ("MYR",)), (r"[元块]", ("CNY",)),
)
_CODES = "|".join(sorted(CURRENCIES, key=len, reverse=True))
_CURRENCY = "|".join([rf"(?<![A-Za-z])(?:{_CODES})(?![A-Za-z])"] + [pattern for pattern, _ in _SYMBOLS])
_NUMBER = r"\d{1,3}(?:[,.  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_AMOUNT = re.compile(rf"(?P<pre>{_CURRENCY})\s?(?P<num>{_NUMBER})(?!\d)|(?<![\d.,])(?P<num2>{_NUMBER})\s?(?P<post>{_CURRENCY})")
_BARE_AMOUNT = re.compile(rf"\b(?:pay|pays|paying|paid|send|sending|transfer|owes?|owed|for|amount(?: due)?|total|of)\s+"
                          rf"(?:me\s+|you\s+|us\s+|the\s+)?(?P<num>{_NUMBER})\s?(?P<k>k\b)?(?![\d/.-])", re.I)

_IN = re.compile(r"\breceived\b|\bcredited\b|\bcredit\b|recebid[oa]|收款|\bdeposit(?:ed)?\b|\bditerima\b|\brecibid[oa]\b|"
                 r"\breçu\b", re.I)
_OUT = re.compile(r"\bdebited\b|\bsent\b|\bspent\b|\bpaid to\b|向.{1,40}?付款|\bwithdrawn?\b|\bpurchase\b|\bdebit\b|"
                  r"\benviad[oa]\b|\bdibayar\b", re.I)
_INVOICE = re.compile(r"\binvoice\b|\bfactura\b|发票|\bnota fiscal\b|\bfacture\b(?!\s+fournisseur)", re.I)
_BILL = re.compile(r"\bbill\b|\btagihan\b|facture fournisseur|amount due|please pay|账单|\bfactura de proveedor\b", re.I)
_PROMISE = re.compile(r"will pay|i'?ll pay|\bte pago\b|\bpagar[ée]\b|saya bayar|akan bayar|de dunga|de denge|\bdibo\b|"
                      r"\d\s*日前付|\bpaierai\b|vou pagar", re.I)
_DUE_BEFORE = re.compile(r"(?:\bdue(?:\s+date)?|\bvence(?:\s+el)?|\bvencimiento|échéance(?:\s+le)?|jatuh tempo|\bpay(?:ment)?\s+by|"
                         r"\bby|\bbefore|\bantes del?|\bavant le|\baté|paling lambat|付款期限|到期日?)\s*[:：]?\s*(?:on\s+|le\s+|el\s+)?$", re.I)
_DUE_AFTER = re.compile(r"^\s*(?:前|之前|\btak\b|\ber moddhe\b|\bmoddhe\b|\bke andar\b)", re.I)
_ISSUE_BEFORE = re.compile(r"(?:\bissued(?:\s+on)?|\bemitida(?:\s+el)?|\bémise(?:\s+le)?|开票日期|\bdated)\s*[:：]?\s*$", re.I)
_INJECTION = re.compile(r"ignore (?:all |any )?(?:previous|prior|earlier) (?:instructions|rules)|\bsystem\s*:|approve (?:the )?payment|"
                        r"transfer all|changed? (?:our |the )?bank|new (?:bank )?account|mark every invoice|without asking|"
                        r"忽略|ignora las instrucciones|abaikan instruksi|ignorez les consignes|ignore as instru", re.I)

_NAME_STOP = (r"(?=\s+(?:on|em|via|for|el|le|pada|tanggal|at\s+\d|will|bill|has|have|is|sent|paid|pays?)\b|\s*[,(:：，。;]|\.\s|\.$|\s*$|"
              r"\s+\d)")
_NAME = r"(?P<who>[A-Z一-鿿][^\n]{0,79}?)"
_PARTY_PATTERNS = [re.compile(pattern, re.I if flags else 0) for pattern, flags in (
    (r"付款方[：:]\s*(?P<who>[^，,。\n]{1,40})", 0),
    (r"向(?P<who>[^，,。¥￥\n]{1,40}?)付款", 0),
    (r"给(?P<who>[^，,。\n]{1,40}?)[，,。]", 0),
    (r"^\s*\[(?:whatsapp|微信|wechat|sms|telegram|signal)\]\s*(?P<who>[^:：\n]{1,80})[:：]", 1),
    (r"^\s*(?P<who>[A-Z一-鿿][^:：\n]{0,79})[:：]\s*(?:bill|invoice|factura|tagihan)\b", 0),
    (r"^\s*(?P<who>[A-Z][^\n]{0,79}?)\s+(?:bill|invoice)\s+[A-Z]{1,5}-?\d", 0),
    (r"^\s*(?P<who>[A-Z][^\n]{0,79}?)\s+(?:will|is going to|promised to)\s+pay\b", 0),
    (r"\b(?:from|by|dari)\s+" + _NAME + _NAME_STOP, 0),
    (r"\bspent\s+at\s+" + _NAME + _NAME_STOP, 0),
    (r"(?<![A-Za-z])(?:de)\s+" + _NAME + _NAME_STOP, 0),
    (r"\b(?:to|para|a)\s+" + _NAME + _NAME_STOP, 0),
)]
_NOT_A_PARTY = re.compile(r"^(?:a/?c\b|acct|account|iban|me|you|us|your|my|our|the|this|pay|payment|ref|upi)\b", re.I)
_REFERENCE = re.compile(r"(?:\bref(?:erence)?\.?\s*(?:no\.?)?\s*[:#]?\s*|\bupi\s*ref\s*no\.?\s*|\bupi\s*:\s*|\bid\s+|transfer\s*#\s*|"
                        r"交易单号|订单号|\binvoice\s+(?:no\.?\s*)?|\bfactura\s+|\bfacture fournisseur\s+|\btagihan\s+|发票|"
                        r"\bbill\s+(?:no\.?\s*)?)(?P<ref>[A-Za-z0-9][A-Za-z0-9/-]{2,30})", re.I)
_CODE_REFERENCE = re.compile(r"\b[A-Z]{2,5}-\d{2,}\b")


def _parse_number(raw):
    text = raw.replace(" ", " ").replace(" ", "")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        text = text.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    elif "," in text:
        text = text.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", text) or not re.search(r",\d{1,2}$", text) \
            else text.replace(",", ".")
    elif text.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", text):
        text = text.replace(".", "")
    value = float(text)
    return int(value) if value == int(value) else round(value, 2)


def _currency(token, business_currency):
    token = token.strip()
    if token.upper() in CURRENCIES and re.fullmatch(r"[A-Za-z]{3}", token):
        return token.upper()
    for pattern, candidates in _SYMBOLS:
        if re.fullmatch(pattern, token):
            return business_currency if business_currency in candidates else candidates[0]
    return business_currency


def _year_for(month, day, today):
    candidate = date(today.year, month, day)
    return candidate if candidate >= today - timedelta(days=90) else date(today.year + 1, month, day)


def _dates(text, today):
    """[(start, end, value, note)] for every date-like phrase; value is ISO, or d/m/YYYY for the shared validator."""
    found, taken = [], []

    def add(match, value, note=None):
        if any(match.start() < end and start < match.end() for start, end in taken):
            return
        taken.append((match.start(), match.end()))
        found.append((match.start(), match.end(), value, note))

    for match in re.finditer(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text):
        add(match, f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}")
    for match in re.finditer(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", text):
        add(match, match.group(0))
    for match in re.finditer(r"(?<![\d.,])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?![\d])", text):
        year = match[3] if len(match[3]) == 4 else f"20{match[3]}"
        add(match, f"{int(match[1]):02d}/{int(match[2]):02d}/{year}")
    for match in re.finditer(rf"(?<!\d)(\d{{1,2}})[\s-]({_MONTH_RE})[\s,-]+(\d{{4}}|\d{{2}})(?![\d:])", text, re.I):
        year = int(match[3]) if len(match[3]) == 4 else 2000 + int(match[3])
        add(match, f"{year:04d}-{_MONTHS[match[2][:3].lower()]:02d}-{int(match[1]):02d}")
    for match in re.finditer(rf"\b({_MONTH_RE})\s+(\d{{1,2}}),?\s+(\d{{4}})(?!\d)", text, re.I):
        add(match, f"{int(match[3]):04d}-{_MONTHS[match[1][:3].lower()]:02d}-{int(match[2]):02d}")
    for match in re.finditer(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text):
        add(match, _year_for(int(match[1]), int(match[2]), today).isoformat(), "year assumed")
    for match in re.finditer(rf"(?<!\d)(\d{{1,2}})\s+({_MONTH_RE})(?![a-z])", text, re.I):
        add(match, _year_for(_MONTHS[match[2][:3].lower()], int(match[1]), today).isoformat(), "year assumed")
    for match in re.finditer(rf"\b({_MONTH_RE})\s+(\d{{1,2}})(?![\d,])", text, re.I):
        add(match, _year_for(_MONTHS[match[1][:3].lower()], int(match[2]), today).isoformat(), "year assumed")
    for match in re.finditer(r"(?<![\d.,/])(\d{1,2})/(\d{1,2})(?![\d/])", text):
        first, second = int(match[1]), int(match[2])
        if 1 <= second <= 12 and 1 <= first <= 31:
            note = "year assumed" + ("; day/month order assumed" if first <= 12 and first != second else "")
            add(match, _year_for(second, first, today).isoformat(), note)
    lowered = text.casefold()
    for words, offset in (((r"today", r"hoy", r"aujourd'hui", r"hoje", r"hari ini", r"今天", r"aaj", r"aj"), 0),
                          ((r"tomorrow", r"mañana", r"demain", r"amanhã", r"besok", r"明天", r"kal", r"kalke"), 1)):
        for match in re.finditer(r"(?<![\w])(?:" + "|".join(words) + r")(?![\w])", lowered):
            add(match, (today + timedelta(days=offset)).isoformat(), "relative date")
    for match in re.finditer(r"\b(?:(next|this|on|by|coming)\s+)?(" + "|".join(_WEEKDAYS) + r")\b", lowered):
        ahead = (_WEEKDAYS.index(match[2]) - today.weekday()) % 7 or 7
        add(match, (today + timedelta(days=ahead)).isoformat(), "relative date")
    for match in re.finditer(r"\bin\s+(\d{1,3})\s+days?\b", lowered):
        add(match, (today + timedelta(days=int(match[1]))).isoformat(), "relative date")
    return sorted(found)


def _party(segment, known):
    folded = segment.casefold()
    hits = [name for name in known if name and name.casefold() in folded]
    if hits:
        return max(hits, key=len)
    for pattern in _PARTY_PATTERNS:
        for match in pattern.finditer(segment):
            who = match.group("who").strip(" \t-–—\"'“”")
            if who.endswith(".") and not re.search(r"(?:\b[A-Za-z]\.|\.[A-Za-z]{1,3}\.)$", who):
                who = who[:-1]
            who = who.strip()
            if 2 <= len(who) <= 80 and not _NOT_A_PARTY.match(who) and not re.fullmatch(r"[\d\W]+", who):
                return who
    return ""


def _reference(segment):
    for match in _REFERENCE.finditer(segment):
        if re.search(r"\d", match["ref"]):
            return match["ref"].rstrip(".-/")
    match = _CODE_REFERENCE.search(segment)
    return match.group(0) if match else None


def _record(segment, business_currency, today, known):
    amounts = list(_AMOUNT.finditer(segment))
    checks = []
    if amounts:
        first = amounts[0]
        number, token = (first["num"], first["pre"]) if first["num"] else (first["num2"], first["post"])
        amount, currency, spans = _parse_number(number), _currency(token, business_currency), [first.span()]
    else:
        bare = _BARE_AMOUNT.search(segment)
        if not bare:
            return None
        amount = _parse_number(bare["num"]) * (1000 if bare["k"] else 1)
        currency, spans = business_currency, [bare.span("num")]
        checks.append(f"no currency in the message: {business_currency} assumed")
    masked = segment
    for start, end in [m.span() for m in amounts] + spans:
        masked = masked[:start] + " " * (end - start) + masked[end:]
    if _INVOICE.search(segment) or _PROMISE.search(segment):
        kind, direction = "invoice", "in"
    elif _BILL.search(segment):
        kind, direction = "bill", "out"
    elif _IN.search(segment):
        kind, direction = "transaction", "in"
    elif _OUT.search(segment):
        kind, direction = "transaction", "out"
    else:
        kind, direction = "transaction", None
        checks.append("could not tell whether money came in or went out: check the type")
    issue = due = when = None
    for start, end, value, note in _dates(masked, today):
        before, after = masked[max(0, start - 30):start], masked[end:end + 12]
        if note:
            checks.append(f"date {value}: {note}")
        if _ISSUE_BEFORE.search(before):
            issue = issue or value
        elif _DUE_BEFORE.search(before) or _DUE_AFTER.search(after):
            due = due or value
        else:
            when = when or value
    if kind == "transaction":
        record_date, due_date = when or issue or due, None
    elif kind == "invoice" and not _PROMISE.search(segment):
        record_date, due_date = issue or when, due or (when if issue else None)
    else:
        record_date, due_date = issue, due or when
    if not (record_date or due_date):
        checks.append("no date found: add one before saving")
    who = _party(segment, known)
    if not who:
        checks.append("no counterparty found: add one before saving")
    return {"record_type": kind, "counterparty": who, "amount": amount, "currency": currency,
            "date": record_date, "due_date": due_date, "direction": direction or "out",
            "reference": _reference(segment), "_checks": checks}


def extract(text, business, today, known_names=()):
    """Same output shape as TideLM's extractor: {"records": [...], "suspicious": bool}."""
    today = date.fromisoformat(str(today)[:10])
    known = sorted({str(name) for name in known_names if name}, key=len, reverse=True)
    records = []
    for segment in re.split(r"[\r\n]+", str(text)):
        if not segment.strip() or _INJECTION.search(segment) and not _AMOUNT.search(segment):
            continue
        record = _record(segment.strip(), business["currency"], today, known)
        if record is not None:
            records.append(record)
        if len(records) >= 20:
            break
    return {"records": records, "suspicious": bool(_INJECTION.search(str(text)))}
