"""Idempotent re-import: importing the same file twice adds 0 rows.

And: two genuinely identical same-day transactions in one file are
both kept (the occurrence index).
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import import_batch, mapping


def _setup() -> int:
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


def test_reimport_same_file_adds_zero_rows() -> None:
    account_id = _setup()
    raw = b"date,description,amount\n2026-10-01,Coffee,-3.50\n2026-10-02,Lunch,-12.00\n"
    m = mapping.Mapping(
        date_col=0, description_col=1, amount_mode="signed", amount_col=2, has_header=True
    )
    with Session(get_engine()) as s:
        b1, _ = import_batch.commit(
            session=s, user_id=1, account_id=account_id, filename="a.csv", raw_bytes=raw, m=m
        )
    with Session(get_engine()) as s:
        b2, _ = import_batch.commit(
            session=s, user_id=1, account_id=account_id, filename="a.csv", raw_bytes=raw, m=m
        )
    assert b1.row_count == 2
    assert b2.row_count == 0
    with Session(get_engine()) as s:
        assert len(s.exec(select(Transaction).where(Transaction.user_id == 1)).all()) == 2


def test_two_identical_same_day_transactions_both_kept() -> None:
    account_id = _setup()
    raw = b"date,description,amount\n2026-10-01,Repeat,-1.00\n2026-10-01,Repeat,-1.00\n"
    m = mapping.Mapping(
        date_col=0, description_col=1, amount_mode="signed", amount_col=2, has_header=True
    )
    with Session(get_engine()) as s:
        batch, _ = import_batch.commit(
            session=s, user_id=1, account_id=account_id, filename="a.csv", raw_bytes=raw, m=m
        )
    assert batch.row_count == 2
    with Session(get_engine()) as s:
        rows = s.exec(select(Transaction).where(Transaction.import_batch_id == batch.id)).all()
    assert len(rows) == 2
    # And the dedup keys are distinct.
    assert rows[0].dedup_key != rows[1].dedup_key
