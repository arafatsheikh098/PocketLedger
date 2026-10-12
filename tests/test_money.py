"""Money parsing table for M1 acceptance criterion A3.

The spec names these exact inputs and the table below pins the expected
output to a single integer value. Any change here is a contract change.
"""
from __future__ import annotations

import pytest

from app.money import MoneyParseError, format, parse


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234.56", 123456),
        ("1234.56", 123456),
        ("1234", 123400),
        ("0", 0),
        ("0.00", 0),
        ("-500", -50000),
        ("-500.00", -50000),
        ("+500", 50000),
        ("(500.00)", -50000),
        ("500-", -50000),
        ("  12.34  ", 1234),
    ],
)
def test_parse_us_default(raw: str, expected: int) -> None:
    assert parse(raw) == expected


def test_parse_european_decimal_comma() -> None:
    # European convention: thousands=".", decimal=",".
    assert parse("1.234,56", decimal_sep=",", thousands_sep=".") == 123456


def test_parse_thousands_with_default_decimal() -> None:
    assert parse("1,234", decimal_sep=".", thousands_sep=",") == 123400


def test_parse_empty_raises() -> None:
    with pytest.raises(MoneyParseError):
        parse("")


def test_parse_none_raises() -> None:
    with pytest.raises(MoneyParseError):
        parse(None)  # type: ignore[arg-type]


def test_parse_float_raises() -> None:
    # Floats are not allowed in money math. The spec says integers only.
    with pytest.raises(MoneyParseError):
        parse(1.23)  # type: ignore[arg-type]


def test_parse_garbage_raises() -> None:
    with pytest.raises(MoneyParseError):
        parse("not money")


def test_format_round_trip() -> None:
    assert format(123456) == "1,234.56"
    assert format(-50000) == "-500.00"
    assert format(0) == "0.00"


def test_format_european() -> None:
    from app.money import MoneyFormat

    assert format(123456, fmt=MoneyFormat(decimal_sep=",", thousands_sep=".")) == "1.234,56"
