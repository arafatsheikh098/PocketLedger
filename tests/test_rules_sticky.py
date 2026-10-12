"""Rules must never overwrite a manual category assignment."""
from __future__ import annotations

from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import rules as rules_service


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


def _cat_id(name: str) -> int:
    with Session(get_engine()) as s:
        c = s.exec(select(Category).where(Category.name == name)).first()
        assert c is not None
        return c.id


def test_manual_category_preserved_on_reapply() -> None:
    uid, account_id = _setup()
    groceries = _cat_id("Groceries")
    transport = _cat_id("Transport")
    with Session(get_engine()) as s:
        # Manually categorized, with manual_category=True.
        s.add(
            Transaction(
                user_id=uid,
                account_id=account_id,
                date=__import__("datetime").date(2026, 10, 1),
                amount_minor=-100,
                currency="USD",
                description="starbucks downtown",
                category_id=transport,  # user chose Transport
                manual_category=True,
                dedup_key="sticky-1",
            )
        )
        s.commit()
    # Add a rule that *would* match the description and assign Groceries.
    with Session(get_engine()) as s:
        s.add(
            Rule(
                user_id=uid,
                pattern="starbucks",
                category_id=groceries,
                position=0,
            )
        )
        s.commit()
    n = rules_service.reapply_uncategorized(Session(get_engine()), uid)
    # The reapply should not touch the sticky transaction; n should be 0.
    assert n == 0
    with Session(get_engine()) as s:
        t = s.exec(select(Transaction).where(Transaction.dedup_key == "sticky-1")).first()
        assert t.category_id == transport
        assert t.manual_category is True
