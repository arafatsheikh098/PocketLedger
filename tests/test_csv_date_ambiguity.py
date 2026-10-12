"""Date format is never guessed: the user must pick one.

Two test files: one with ISO (unambiguous) and one with 03/04/2026
style dates. The latter can only be parsed with an explicit
``%d/%m/%Y`` or ``%m/%d/%Y`` chosen by the user.
"""
from __future__ import annotations

from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
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


def test_iso_date_unambiguous() -> None:
    aid = _setup()
    raw = b"date,description,amount\n2026-04-03,Coffee,-3.50\n"
    m = mapping.Mapping(date_col=0, description_col=1, amount_mode="signed", amount_col=2)
    with Session(get_engine()) as s:
        result = import_batch.dry_run(session=s, user_id=1, account_id=aid, raw_bytes=raw, m=m)
    assert result.error_count == 0
    new = [r for r in result.rows if r.status == "new"][0]
    assert new.date.isoformat() == "2026-04-03"


def test_ambiguous_date_requires_explicit_choice() -> None:
    aid = _setup()
    raw = b"date,description,amount\n03/04/2026,Coffee,-3.50\n"
    # Pick the day-first format explicitly.
    m = mapping.Mapping(
        date_col=0, description_col=1, amount_mode="signed", amount_col=2, date_format="%d/%m/%Y"
    )
    with Session(get_engine()) as s:
        result = import_batch.dry_run(session=s, user_id=1, account_id=aid, raw_bytes=raw, m=m)
    assert result.error_count == 0
    new = [r for r in result.rows if r.status == "new"][0]
    assert new.date.isoformat() == "2026-04-03"  # 3 April
    # Same data with month-first gives 3 March.
    m2 = mapping.Mapping(
        date_col=0, description_col=1, amount_mode="signed", amount_col=2, date_format="%m/%d/%Y"
    )
    with Session(get_engine()) as s:
        result2 = import_batch.dry_run(
            session=s, user_id=1, account_id=aid, raw_bytes=raw, m=m2
        )
    assert result2.error_count == 0
    new2 = [r for r in result2.rows if r.status == "new"][0]
    assert new2.date.isoformat() == "2026-03-04"  # 4 March
