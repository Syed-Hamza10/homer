import ast
import math
import operator
import re
from dataclasses import dataclass
from typing import Any

MAX_EXPONENT = 64
MAX_TEXT = 120
NUMBER = r"\d[\d,]*(?:\.\d+)?|\.\d+"
LEAD = re.compile(
    r"^(?:(?:hey|ok|okay|quick q|quick question|so|and|please|pls)[,:]?\s+)*"
    r"(?:what(?:'s|’s| is| are)|whats|how much is|how much are|calculate|compute|work out"
    r"|can you (?:calculate|compute|work out)|tell me|convert|solve)?\s*",
    re.IGNORECASE,
)
WORDS = [
    (r"\bmultiplied by\b|\btimes\b|×|\bx\b", "*"),
    (r"\bdivided by\b|\bover\b|÷", "/"),
    (r"\bplus\b|\badded to\b", "+"),
    (r"\bminus\b|\bless\b", "-"),
    (r"\bto the power of\b|\^", "**"),
    (r"\bsquared\b", "**2"),
    (r"\bcubed\b", "**3"),
    (r"\bsquare root of\s+(" + NUMBER + ")", r"sqrt(\1)"),
    (r"\$|\b(?:dollars?|bucks|euros?|rupees?)\b", ""),
    (r"(" + NUMBER + r")\s*(?:%|percent)\s+off\s+(" + NUMBER + ")", r"\2*(1-\1/100)"),
    (
        r"(" + NUMBER + r")\s*(?:%|percent)\s+(?:tip|tax|discount|vat)?\s*(?:of|on|for)\b",
        r"(\1/100)*",
    ),
    (r"\bmod(?:ulo)?\b", "%"),
]
EXPRESSION = re.compile(r"^[\d\s.+\-*/()%,sqrt]+$")
OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

LENGTH = {
    "mm": 0.001,
    "millimeter": 0.001,
    "millimetre": 0.001,
    "cm": 0.01,
    "centimeter": 0.01,
    "centimetre": 0.01,
    "m": 1.0,
    "meter": 1.0,
    "metre": 1.0,
    "km": 1000.0,
    "kilometer": 1000.0,
    "kilometre": 1000.0,
    "in": 0.0254,
    "inch": 0.0254,
    "inches": 0.0254,
    "ft": 0.3048,
    "foot": 0.3048,
    "feet": 0.3048,
    "yd": 0.9144,
    "yard": 0.9144,
    "mi": 1609.344,
    "mile": 1609.344,
}
MASS = {
    "mg": 0.000001,
    "g": 0.001,
    "gram": 0.001,
    "kg": 1.0,
    "kilo": 1.0,
    "kilogram": 1.0,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "pound": 0.45359237,
    "oz": 0.028349523125,
    "ounce": 0.028349523125,
    "stone": 6.35029318,
    "st": 6.35029318,
    "tonne": 1000.0,
}
VOLUME = {
    "ml": 0.001,
    "milliliter": 0.001,
    "millilitre": 0.001,
    "l": 1.0,
    "liter": 1.0,
    "litre": 1.0,
    "gallon": 3.785411784,
    "gal": 3.785411784,
    "cup": 0.2365882365,
    "pint": 0.473176473,
    "quart": 0.946352946,
}
SPEED = {"kmh": 1.0, "kph": 1.0, "km/h": 1.0, "mph": 1.609344, "m/s": 3.6}
DIMENSIONS = [LENGTH, MASS, VOLUME, SPEED]
TEMPERATURE = {
    "c": "C",
    "celsius": "C",
    "centigrade": "C",
    "f": "F",
    "fahrenheit": "F",
    "k": "K",
    "kelvin": "K",
}
CURRENCIES = {
    "USD": ("usd", "$", "us dollar", "dollar", "us$", "buck"),
    "EUR": ("eur", "€", "euro"),
    "GBP": ("gbp", "£", "british pound", "pound sterling", "sterling", "pound"),
    "PKR": ("pkr", "pakistani rupee", "rupee", "rs"),
    "INR": ("inr", "indian rupee", "₹"),
    "JPY": ("jpy", "¥", "yen", "japanese yen"),
    "CAD": ("cad", "canadian dollar"),
    "AUD": ("aud", "australian dollar"),
    "AED": ("aed", "dirham", "uae dirham"),
    "SAR": ("sar", "riyal", "saudi riyal"),
    "CHF": ("chf", "swiss franc", "franc"),
    "CNY": ("cny", "yuan", "rmb", "renminbi"),
    "SEK": ("sek", "swedish krona", "krona", "kronor"),
    "TRY": ("try", "turkish lira", "lira"),
}
SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
UNIT = r"[a-z$€£¥₹/][a-z$€£¥₹/ .]*?"
CONVERT = [
    re.compile(
        rf"^(?P<symbol>[$€£¥₹])?\s*(?P<amount>{NUMBER})\s*(?P<source>{UNIT})?\s+"
        rf"(?:to|in|into|as|=)\s+(?P<target>{UNIT})\s*[?.!]*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^how many (?P<target>{UNIT})\s+(?:is|are|in|=|for|do i get for|would i get for)\s+"
        rf"(?P<symbol>[$€£¥₹])?\s*(?P<amount>{NUMBER})\s*(?P<source>{UNIT})?\s*[?.!]*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^how many (?P<target>{UNIT})\s+(?:are\s+)?in\s+(?:a|an|one)\s+(?P<source>{UNIT})"
        r"\s*[?.!]*$",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class Arithmetic:
    expression: str
    value: float


@dataclass(frozen=True)
class UnitConversion:
    amount: float
    source: str
    target: str
    value: float


@dataclass(frozen=True)
class CurrencyConversion:
    amount: float
    source: str
    target: str


Calculation = Arithmetic | UnitConversion | CurrencyConversion


def number(text: str) -> float:
    return float(text.replace(",", ""))


def shown(value: float) -> str:
    """Thousands separators, no trailing zeros, at most 4 decimals."""
    if value == int(value) and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def evaluate(node: ast.AST) -> float:
    match node:
        case ast.Expression(body=body):
            return evaluate(body)
        case ast.Constant(value=int() | float() as value):
            return float(value)
        case ast.UnaryOp(op=op, operand=operand) if type(op) in OPERATORS:
            return OPERATORS[type(op)](evaluate(operand))
        case ast.BinOp(left=left, op=ast.Pow(), right=right):
            base, exponent = evaluate(left), evaluate(right)
            if abs(exponent) > MAX_EXPONENT:
                raise ValueError("exponent too large")
            return float(base**exponent)
        case ast.BinOp(left=left, op=op, right=right) if type(op) in OPERATORS:
            return OPERATORS[type(op)](evaluate(left), evaluate(right))
        case ast.Call(func=ast.Name(id="sqrt"), args=[argument], keywords=[]):
            return math.sqrt(evaluate(argument))
    raise ValueError("unsupported expression")


def arithmetic(text: str) -> Arithmetic | None:
    """A sum written in digits and operator words, such as 'what is 17 times 23'."""
    written = LEAD.sub("", text.strip().lower(), count=1).rstrip(" ?.!=")
    body = written
    for pattern, replacement in WORDS:
        body = re.sub(pattern, replacement, body)
    body = re.sub(r"(?<=\d),(?=\d{3})", "", body).strip()
    if not EXPRESSION.match(body) or not re.search(r"\d\s*(?:[-+*/%]|\*\*)\s*[\d(s]|sqrt\(", body):
        return None
    try:
        value = evaluate(ast.parse(body, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    return Arithmetic(re.sub(r"\s+", " ", written), value)


def singular(unit: str) -> str:
    unit = unit.strip().lower().rstrip(".")
    unit = re.sub(r"^(?:degrees?|deg|°)\s*", "", unit).replace("°", "")
    for suffix in ("es", "s"):
        if unit.endswith(suffix) and len(unit) > len(suffix) + 1 and unit not in ("lbs", "gas"):
            trimmed = unit[: -len(suffix)]
            if any(trimmed in table for table in DIMENSIONS) or trimmed in TEMPERATURE:
                return trimmed
            if any(trimmed in aliases for aliases in CURRENCIES.values()):
                return trimmed
    return unit


def currency(unit: str) -> str | None:
    unit = singular(unit)
    if unit.upper() in CURRENCIES:
        return unit.upper()
    for code, aliases in CURRENCIES.items():
        if unit in aliases:
            return code
    return None


def celsius(value: float, scale: str) -> float:
    return {"C": value, "F": (value - 32) * 5 / 9, "K": value - 273.15}[scale]


def from_celsius(value: float, scale: str) -> float:
    return {"C": value, "F": value * 9 / 5 + 32, "K": value + 273.15}[scale]


def unit_value(amount: float, source: str, target: str) -> float | None:
    if source in TEMPERATURE and target in TEMPERATURE:
        return from_celsius(celsius(amount, TEMPERATURE[source]), TEMPERATURE[target])
    for table in DIMENSIONS:
        if source in table and target in table:
            return amount * table[source] / table[target]
    return None


def conversion(text: str) -> UnitConversion | CurrencyConversion | None:
    body = LEAD.sub("", text.strip(), count=1)
    for pattern in CONVERT:
        match = pattern.match(body)
        if match is None:
            continue
        fields = match.groupdict()
        amount = number(fields.get("amount") or "1")
        source_text = fields["source"] or ""
        target_text = fields["target"]
        source = SYMBOLS.get(fields.get("symbol") or "") or currency(source_text)
        target = currency(target_text)
        if source and target and source != target:
            return CurrencyConversion(amount, source, target)
        source_unit, target_unit = singular(source_text), singular(target_text)
        value = unit_value(amount, source_unit, target_unit)
        if value is not None:
            return UnitConversion(amount, source_text.strip(), target_text.strip(), value)
    return None


def parse(text: str) -> Calculation | None:
    """A sum or a unit or currency conversion the whole message asks for, else None."""
    if len(text) > MAX_TEXT:
        return None
    return conversion(text) or arithmetic(text)


RATE_PATTERN = (
    r"1(?:\.0+)?\s*(?:{source})\s*(?:=|equals|is|to|→|->)\s*(?:{target_symbol})?\s*"
    r"(?P<rate>\d+(?:[.,]\d+)?)\s*(?:{target})"
)


def aliases(code: str) -> str:
    names = sorted({code.lower(), *CURRENCIES[code]}, key=len, reverse=True)
    return "|".join(re.escape(name) + r"s?" for name in names)


def find_rate(text: str, source: str, target: str) -> float | None:
    """Reads '1 USD = 0.8671 EUR' (or the names spelled out) from search snippets."""
    symbol = "|".join(re.escape(s) for s, code in SYMBOLS.items() if code == target) or "(?!)"
    pattern = RATE_PATTERN.format(
        source=aliases(source), target=aliases(target), target_symbol=symbol
    )
    match = re.search(pattern, text, re.IGNORECASE)
    if match is None:
        return None
    rate = float(match["rate"].replace(",", "."))
    return rate if rate > 0 else None
