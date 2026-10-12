"""Row-level error reporting and the dry-run-writes-nothing rule."""
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


def test_dry_run_writes_nothing() -> None:
    account_id = _setup()
    raw = b"date,description,amount\n2026-10-01,Coffee,-3.50\n"
    m = mapping.Mapping(date_col=0, description_col=1, amount_mode="signed", amount_col=2)
    with Session(get_engine()) as s:
        import_batch.dry_run(session=s, user_id=1, account_id=account_id, raw_bytes=raw, m=m)
    with Session(get_engine()) as s:
        rows = s.exec(select(Transaction).where(Transaction.user_id == 1)).all()
    assert rows == []


def test_row_error_reported_with_line_number() -> None:
    account_id = _setup()
    # Line 2 has a non-numeric amount.
    raw = b"date,description,amount\n2026-10-01,Bad,bad-value\n2026-10-02,Good,-1.00\n"
    m = mapping.Mapping(date_col=0, description_col=1, amount_mode="signed", amount_col=2)
    with Session(get_engine()) as s:
        result = import_batch.dry_run(
            session=s, user_id=1, account_id=account_id, raw_bytes=raw, m=m
        )
    errors = [r for r in result.rows if r.status == "error"]
    assert len(errors) == 1
    assert errors[0].line_number == 1  # 0-indexed file line 1 = "Bad"
    # The good row still imports.
    with Session(get_engine()) as s:
        batch, _ = import_batch.commit(
            session=s, user_id=1, account_id=account_id, filename="x.csv", raw_bytes=raw, m=m,
            skip_errors=True,
        )
    assert batch.row_count == 1
    with Session(get_engine()) as s:
        rows = s.exec(select(Transaction).where(Transaction.import_batch_id == batch.id)).all()
    assert len(rows) == 1
    assert rows[0].description == "Good"
