"""Undo: removes exactly the rows a batch added."""
from __future__ import annotations

from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.import_batch import ImportBatch
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import import_batch, mapping


def _setup() -> tuple[int, int]:
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
        return u.id, a.id


def test_undo_removes_exactly_batch_rows() -> None:
    uid, account_id = _setup()
    raw = b"date,description,amount\n2026-10-01,A,-1.00\n2026-10-02,B,-2.00\n"
    m = mapping.Mapping(
        date_col=0, description_col=1, amount_mode="signed", amount_col=2, has_header=True
    )
    with Session(get_engine()) as s:
        b, _ = import_batch.commit(
            session=s, user_id=uid, account_id=account_id, filename="x.csv", raw_bytes=raw, m=m
        )
    # Now add a manual row that must NOT be removed by the undo.
    with Session(get_engine()) as s:
        s.add(
            Transaction(
                user_id=uid,
                account_id=account_id,
                date=__import__("datetime").date(2026, 10, 5),
                amount_minor=-999,
                currency="USD",
                description="manual",
                dedup_key="manual-key",
            )
        )
        s.commit()
    with Session(get_engine()) as s:
        n = import_batch.undo(s, uid, b.id)
    assert n == 2
    with Session(get_engine()) as s:
        rows = s.exec(select(Transaction).where(Transaction.user_id == uid)).all()
    assert len(rows) == 1
    assert rows[0].description == "manual"
    with Session(get_engine()) as s:
        batch = s.get(ImportBatch, b.id)
    assert batch.undone is True


def test_undo_idempotent() -> None:
    uid, account_id = _setup()
    raw = b"date,description,amount\n2026-10-01,A,-1.00\n"
    m = mapping.Mapping(
        date_col=0, description_col=1, amount_mode="signed", amount_col=2, has_header=True
    )
    with Session(get_engine()) as s:
        b, _ = import_batch.commit(
            session=s, user_id=uid, account_id=account_id, filename="x.csv", raw_bytes=raw, m=m
        )
    with Session(get_engine()) as s:
        n1 = import_batch.undo(s, uid, b.id)
    assert n1 == 1
    with Session(get_engine()) as s:
        n2 = import_batch.undo(s, uid, b.id)
    assert n2 == 0
