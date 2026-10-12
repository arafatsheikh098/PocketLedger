"""Golden-file import test for the 6 messy CSV fixtures.

For every fixture, we read the file, build a mapping based on the
expected JSON, run dry-run, then commit, and verify the database has
exactly the expected transactions.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import import_batch, mapping

FIXTURES = Path(__file__).parent / "fixtures"
EXPECTED = FIXTURES / "expected"


def _make_user() -> int:
    with Session(get_engine()) as s:
        u = User(
            username="alice",
            password_hash=hash_password("pw12345678"),
            base_currency="USD",
            timezone="UTC",
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        _seed_default_categories(s, u.id)
        a = Account(user_id=u.id, name="Checking", type="bank")
        s.add(a)
        s.commit()
        s.refresh(a)
        return a.id


def _build_mapping(spec: dict) -> mapping.Mapping:
    if spec["amount_mode"] == "signed":
        return mapping.Mapping(
            date_col=0,
            description_col=1,
            amount_mode="signed",
            amount_col=2,
            date_format=spec["date_format"],
            decimal_sep=spec.get("decimal_sep", "."),
            thousands_sep=spec.get("thousands_sep", ","),
        )
    return mapping.Mapping(
        date_col=0,
        description_col=1,
        amount_mode="debit_credit",
        debit_col=2,
        credit_col=3,
        date_format=spec["date_format"],
        decimal_sep=spec.get("decimal_sep", "."),
        thousands_sep=spec.get("thousands_sep", ","),
        expenses_are_positive=spec.get("expenses_are_positive", True),
    )


@pytest.mark.parametrize(
    "name",
    [
        "us_iso_signed",
        "eu_semicolon_decimal",
        "debit_credit",
        "uk_dayfirst",
        "thousands_separator",
        "quoted_commas_trailing",
    ],
)
def test_fixture_imports_to_expected_rows(name: str) -> None:
    raw = (FIXTURES / f"{name}.csv").read_bytes()
    spec = json.loads((EXPECTED / f"{name}.json").read_text())
    account_id = _make_user()
    m = _build_mapping(spec)
    with Session(get_engine()) as s:
        result = import_batch.dry_run(
            session=s, user_id=1, account_id=account_id, raw_bytes=raw, m=m
        )
    expected_new = [r for r in spec["rows"] if r["status"] == "new"]
    assert result.new_count == len(expected_new)
    assert result.error_count == 0
    for actual, exp in zip(
        sorted(
            [r for r in result.rows if r.status == "new"],
            key=lambda r: (r.date, r.description),
        ),
        sorted(expected_new, key=lambda r: (r["date"], r["description"])), strict=False,
    ):
        assert actual.date.isoformat() == exp["date"]
        assert actual.description == exp["description"]
        assert actual.amount_minor == exp["amount_minor"]
        assert actual.is_transfer == exp["is_transfer"]

    # Commit and verify the DB rows.
    with Session(get_engine()) as s:
        batch, errors = import_batch.commit(
            session=s,
            user_id=1,
            account_id=account_id,
            filename=f"{name}.csv",
            raw_bytes=raw,
            m=m,
            skip_errors=True,
        )
    assert not errors
    with Session(get_engine()) as s:
        rows = s.exec(
            select(Transaction).where(Transaction.import_batch_id == batch.id)
        ).all()
    assert len(rows) == len(expected_new)
    for actual, exp in zip(
        sorted(rows, key=lambda r: (r.date, r.description)),
        sorted(expected_new, key=lambda r: (r["date"], r["description"])), strict=False,
    ):
        assert actual.date.isoformat() == exp["date"]
        assert actual.description == exp["description"]
        assert actual.amount_minor == exp["amount_minor"]
