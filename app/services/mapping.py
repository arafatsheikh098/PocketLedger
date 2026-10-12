"""Mapping profiles for CSV import.

A mapping profile says: which column is the date, which is the
description, how amounts are encoded (single signed, or debit/credit
split), which decimal and thousands separators to use, and which
date format the bank uses.

Date format is always a user-chosen ``strptime`` template — never
guessed between ambiguous formats like 03/04/2026.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Literal

from ..money import MoneyParseError, parse

# Per F4 the date format is always a user choice; we support a small
# whitelist of explicit formats, never ambiguous ones like MM/DD vs DD/MM
# (the user picks one).
DATE_FORMATS = (
    "%Y-%m-%d",  # ISO
    "%Y/%m/%d",
    "%d/%m/%Y",  # explicit day-first
    "%m/%d/%Y",  # explicit month-first
    "%d.%m.%Y",  # German
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%Y%m%d",
    "%d %b %Y",  # 12 Jan 2026
    "%b %d, %Y",  # Jan 12, 2026
)


@dataclass
class Mapping:
    date_col: int
    description_col: int
    amount_mode: Literal["signed", "debit_credit"]
    amount_col: int | None = None
    debit_col: int | None = None
    credit_col: int | None = None
    is_transfer_col: int | None = None
    notes_col: int | None = None
    date_format: str = "%Y-%m-%d"
    decimal_sep: str = "."
    thousands_sep: str = ","
    # If True, amounts in the file are expenses; we sign-flip them.
    expenses_are_positive: bool = True
    # Skip the first row (treat it as a header).
    has_header: bool = True

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, blob: str) -> Mapping:
        return cls(**json.loads(blob))


class RowError(ValueError):
    """Raised for per-row import errors (parse failure, missing value)."""


def parse_date(value: str, fmt: str) -> date:
    try:
        return datetime.strptime(value.strip(), fmt).date()
    except (ValueError, TypeError) as exc:
        raise RowError(f"date {value!r} does not match format {fmt!r}") from exc


def parse_amount(
    raw_value: str,
    *,
    mode: str,
    mapping: Mapping,
) -> int:
    """Parse one amount cell into signed integer minor units.

    ``mode`` is the per-row mode the user picks. For a signed column,
    ``mode`` is the column index; for debit/credit it is unused.
    """
    if mapping.amount_mode == "signed":
        if mapping.amount_col is None:
            raise RowError("mapping is missing amount_col")
        try:
            return parse(
                raw_value,
                decimal_sep=mapping.decimal_sep,
                thousands_sep=mapping.thousands_sep,
            )
        except MoneyParseError as exc:
            raise RowError(f"amount {raw_value!r}: {exc}") from exc
    if mapping.amount_mode == "debit_credit":
        if mapping.debit_col is None or mapping.credit_col is None:
            raise RowError("mapping is missing debit/credit columns")
        # Caller must pass the joined debit/credit string. Use a special form:
        # value is "<debit>|<credit>".
        debit_raw, credit_raw = raw_value.split("|", 1)
        debit = parse(
            debit_raw.strip(),
            decimal_sep=mapping.decimal_sep,
            thousands_sep=mapping.thousands_sep,
        ) if debit_raw.strip() else 0
        credit = parse(
            credit_raw.strip(),
            decimal_sep=mapping.decimal_sep,
            thousands_sep=mapping.thousands_sep,
        ) if credit_raw.strip() else 0
        # Banks vary: some write debits as positive, some as negative.
        # Convention: credit is income (positive), debit is expense
        # (negative). We always treat the unsigned magnitudes as the
        # sign driver. The user can flip with "expenses_are_positive".
        if mapping.expenses_are_positive:
            return -abs(debit) + abs(credit)
        return abs(debit) - abs(credit)
    raise RowError(f"unknown amount mode: {mapping.amount_mode}")


def normalize_for_dedup(description: str) -> str:
    """Exposed for tests; the real normalization lives in app.services.dedup."""
    from .dedup import normalize_description

    return normalize_description(description)
