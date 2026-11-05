import pytest

from homer_core.services.calc import (
    Arithmetic,
    CurrencyConversion,
    UnitConversion,
    find_rate,
    parse,
    shown,
)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("what is 17 times 23", 391),
        ("whats 15% of 80?", 12),
        ("calculate (3+4)*2", 14),
        ("2^10", 1024),
        ("square root of 144", 12),
        ("what is 10 divided by 4?", 2.5),
        ("1,200 + 34", 1234),
    ],
)
def test_sums_are_computed_in_code(text: str, value: float) -> None:
    found = parse(text)
    assert isinstance(found, Arithmetic) and found.value == value


@pytest.mark.parametrize(
    "text",
    [
        "what is 2026",
        "what's the capital of Australia",
        "explain REST",
        "no",
        "what is 9**999999",
        "__import__('os').system('ls')",
        "email Bob that 3 x 4 is 12",
    ],
)
def test_other_messages_are_not_sums(text: str) -> None:
    assert parse(text) is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("10 miles to km", 16.09344),
        ("how many kg is 150 lbs", 68.0388555),
        ("30c to f", 86),
        ("convert 5 feet to cm", 152.4),
        ("100 pounds to kg", 45.359237),
    ],
)
def test_units_are_converted(text: str, value: float) -> None:
    found = parse(text)
    assert isinstance(found, UnitConversion) and found.value == pytest.approx(value)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("how many euros is 3,400 US dollars", CurrencyConversion(3400, "USD", "EUR")),
        ("convert 100 usd to eur", CurrencyConversion(100, "USD", "EUR")),
        ("$50 in pounds", CurrencyConversion(50, "USD", "GBP")),
        ("100 pounds to dollars", CurrencyConversion(100, "GBP", "USD")),
    ],
)
def test_currencies_are_recognised(text: str, expected: CurrencyConversion) -> None:
    assert parse(text) == expected


def test_rates_are_read_from_snippets() -> None:
    assert find_rate("Nov 6, 2026: 1 USD = 0.8671 EUR", "USD", "EUR") == 0.8671
    assert find_rate("1 US Dollar equals 0.87 Euro", "USD", "EUR") == 0.87
    assert find_rate("Live euro rates and charts", "USD", "EUR") is None


def test_numbers_are_shown_plainly() -> None:
    assert (shown(391.0), shown(2948.123456), shown(1 / 3)) == ("391", "2,948.1235", "0.3333")
