"""Integer money helpers.

All money in the app is stored and computed as integer minor units
(for example cents). This module is the only place that knows about
the human string representation, and the only place where floats
are intentionally used (and only for parsing/formatting).

Design goals:
  * Round-trip stability: format(parse(x)) == x for canonical inputs.
  * No silent loss of precision: every parse either succeeds with an
    explicit integer result, or raises MoneyParseError.
  * Configurable decimal and thousands separators.
  * Handles US, European and accounting-style inputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class MoneyParseError(ValueError):
    """Raised when a money string cannot be parsed to integer minor units."""


@dataclass(frozen=True)
class MoneyFormat:
    decimal_sep: str = "."
    thousands_sep: str = ","
    currency_symbol: str = ""
    # If true, the formatted minor units are not scaled (assume already
    # in minor units when formatting). Always True in this app; we only
    # format integer minor units.
    minor_units: bool = True


def parse(
    value: str | int | float | None,
    *,
    decimal_sep: str = ".",
    thousands_sep: str = ",",
) -> int:
    """Parse a money string into integer minor units.

    Examples (with default decimal=".", thousands=","):
        "1,234.56"   -> 123456
        "1234.56"    -> 123456
        "1234"       -> 123400
        "-500"       -> -50000
        "(500.00)"   -> -50000     # accounting style
        "500-"       -> -50000     # trailing minus
        "1.234,56"   -> ERROR (with default seps)
        ""           -> ERROR
        None         -> ERROR

    European example (decimal=",", thousands="."):
        "1.234,56"   -> 123456
    """
    if value is None:
        raise MoneyParseError("money value is None")
    if isinstance(value, bool):
        raise MoneyParseError("money value is a bool")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # Explicit rejection: floats are not allowed in money math.
        raise MoneyParseError("float money values are not allowed")

    s = str(value).strip()
    if s == "":
        raise MoneyParseError("empty money value")

    sign = 1
    body = s

    # Accounting parentheses "(123.45)" -> negative.
    if body.startswith("(") and body.endswith(")"):
        sign = -1
        body = body[1:-1].strip()

    # Trailing minus "123.45-" -> negative.
    if body.endswith("-"):
        sign = -sign
        body = body[:-1].strip()

    if body.startswith("+"):
        body = body[1:].strip()
    if body.startswith("-"):
        sign = -sign
        body = body[1:].strip()

    # Remove currency symbols and spaces inside (e.g. "$ 1,234.56").
    body = re.sub(r"[^\d\.,]", "", body)
    if body == "":
        raise MoneyParseError(f"money value has no digits: {value!r}")

    if thousands_sep and thousands_sep in body:
        body = body.replace(thousands_sep, "")

    # Normalize decimal separator to "."
    if decimal_sep != "." and decimal_sep in body:  # noqa: SIM102
        body = body.replace(decimal_sep, ".")
    # If both "." and "," appear, the chosen decimal_sep wins. If the
    # chosen decimal_sep is "." and the remaining string has a comma,
    # that comma was a thousands separator and was already stripped.

    # Now body must match \d+(\.\d+)?
    if not re.fullmatch(r"\d+(\.\d+)?", body):
        raise MoneyParseError(f"unparseable money value: {value!r}")

    if "." in body:
        major, minor = body.split(".")
        # Pad or truncate minor to exactly 2 digits.
        if len(minor) == 1:
            minor = minor + "0"
        elif len(minor) > 2:
            minor = minor[:2]
    else:
        major, minor = body, "00"

    try:
        return sign * (int(major) * 100 + int(minor))
    except ValueError as exc:  # pragma: no cover - guarded by regex
        raise MoneyParseError(f"unparseable money value: {value!r}") from exc


def to_minor(major_units: int) -> int:
    """Convert an integer number of major units to minor units.

    Example: to_minor(5) -> 500.
    """
    return int(major_units) * 100


def from_minor(amount_minor: int) -> int:
    """Convert integer minor units to integer major units (truncated)."""
    return int(amount_minor) // 100


def format(amount_minor: int, *, fmt: MoneyFormat | None = None) -> str:
    """Format integer minor units for display.

    Output is in the chosen decimal/thousands convention. No currency
    symbol is added unless fmt.currency_symbol is set; the spec says
    each user has one base currency and the UI shows it, not the helper.
    """
    if fmt is None:
        fmt = MoneyFormat()
    sign = "-" if amount_minor < 0 else ""
    n = abs(int(amount_minor))
    major, minor = divmod(n, 100)
    major_str = str(major)
    if fmt.thousands_sep:
        # Insert thousands separator from the right.
        parts = []
        while len(major_str) > 3:
            parts.append(major_str[-3:])
            major_str = major_str[:-3]
        parts.append(major_str)
        major_str = fmt.thousands_sep.join(reversed(parts))
    if fmt.currency_symbol:
        return f"{sign}{fmt.currency_symbol}{major_str}{fmt.decimal_sep}{minor:02d}"
    return f"{sign}{major_str}{fmt.decimal_sep}{minor:02d}"


def safe_parse(value: str | int | float | None, default: int = 0, **kw: object) -> int:
    """Like parse() but returns default instead of raising.

    Used at boundaries where the spec says invalid amounts are reported
    per row rather than aborting the whole import.
    """
    try:
        return parse(value, **kw)  # type: ignore[arg-type]
    except MoneyParseError:
        return default
