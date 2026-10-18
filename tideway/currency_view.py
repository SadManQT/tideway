"""Illustrative currency presentation and explicit input normalization.

No rates are fetched, no FX trade is created and no signed document is rewritten.
"""
from fractions import Fraction
import re
from .domain import CURRENCIES, MAX_AMOUNT_MINOR, ValidationError, money_text


def code(value):
    if not isinstance(value,str) or value not in CURRENCIES:
        raise ValidationError("Choose a supported currency.")
    return value


def convert(minor, source, target):
    code(source);code(target)
    if isinstance(minor,bool) or not isinstance(minor,int):raise ValidationError("An integer money amount is required.")
    value=Fraction(abs(minor))*Fraction(str(CURRENCIES[target][1]))/Fraction(str(CURRENCIES[source][1]))
    q,r=divmod(value.numerator,value.denominator)
    return (-1 if minor<0 else 1)*(q+(2*r>=value.denominator))


def display(minor, source, target=None):
    target=source if target is None else code(target)
    amount=convert(minor,source,target)
    if source!=target and minor and not amount:
        return f"≈ {'−' if minor<0 else ''}{target} < 0.01"
    return ("≈ " if target!=source else "")+money_text(amount,target)


AMOUNT=re.compile(r"(?<![\w])(?P<sign>[−-]?)(?P<code>[A-Z]{3})\s*(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?!(?:\w|,\d|\.\d|[-/]\d))",re.I)


def question(message, input_currency, ledger_currency, protected=(), *, require_explicit=True):
    """Convert explicitly coded monetary tokens; never reinterpret days, IDs or bare amounts."""
    code(input_currency);code(ledger_currency)
    if not isinstance(message,str) or len(message)>2000:raise ValidationError("Use a question up to 2,000 characters.")
    ranges=[]
    for name in protected:
        if not name:continue
        ranges.extend((m.start(),m.end()) for m in re.finditer(re.escape(name),message,re.I))
    matches=[m for m in AMOUNT.finditer(message) if m['code'].upper() in CURRENCIES and not any(m.start()<b and m.end()>a for a,b in ranges)]
    masked=list(message)
    for a,b in ranges+[(m.start(),m.end()) for m in matches]:masked[a:b]=' '*(b-a)
    remaining=''.join(masked)
    # Structured identifiers and contact details are not unlabelled money.
    remaining=re.sub(r'\b[A-Z][A-Z_]*-\d[\w-]*\b|[\w.+-]+@[\w.-]+\.[A-Z]{2,}|(?<!\w)\+\d{8,15}(?!\w)', ' ', remaining, flags=re.I)
    # A foreign-unit question must name its monetary units. Dates/time/percent terms are not money.
    remaining=re.sub(r'\b\d{4}-\d{2}-\d{2}\b|\b\d+(?:\.\d+)?\s*(?:days?\b|weeks?\b|months?\b|hours?\b|din\b|দিন|天|周|月|দিন|dias?\b|jours?\b|hari\b|minggu\b|%|basis points?\b|bps\b)', ' ', remaining, flags=re.I)
    if require_explicit and input_currency!=ledger_currency and re.search(r'\d',remaining):
        raise ValidationError(f"Include a currency code for money, for example {input_currency} 100. Days and percentages can stay as numbers.")
    result=message
    for m in reversed(matches):
        if m['sign']:raise ValidationError("Use a nonnegative amount in a financial question.")
        amount=Fraction(m['amount'].replace(',',''))*100
        if amount.denominator!=1:raise ValidationError("Use at most two decimal places.")
        n=convert(amount.numerator,m['code'].upper(),ledger_currency)
        if not 0<n<=MAX_AMOUNT_MINOR:raise ValidationError("Question amount is outside supported ledger limits.")
        result=result[:m.start()]+money_text(n,ledger_currency)+result[m.end():]
    return result
