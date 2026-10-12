"""Re-apply only touches uncategorized, non-sticky transactions."""
from __future__ import annotations

import datetime

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


def test_reapply_only_uncategorized() -> None:
    uid, account_id = _setup()
    groceries = _cat_id("Groceries")
    transport = _cat_id("Transport")
    with Session(get_engine()) as s:
        # Already categorized (system, not manual) - must NOT be re-categorized
        s.add(
            Transaction(
                user_id=uid,
                account_id=account_id,
                date=datetime.date(2026, 10, 1),
                amount_minor=-100,
                currency="USD",
                description="starbucks downtown",
                category_id=transport,
                manual_category=False,
                dedup_key="sys-1",
            )
        )
        # Uncategorized - SHOULD be matched
        s.add(
            Transaction(
                user_id=uid,
                account_id=account_id,
                date=datetime.date(2026, 10, 2),
                amount_minor=-200,
                currency="USD",
                description="STARBUCKS AIRPORT",
                category_id=None,
                manual_category=False,
                dedup_key="uncat-1",
            )
        )
        # Sticky manual - must NOT change
        s.add(
            Transaction(
                user_id=uid,
                account_id=account_id,
                date=datetime.date(2026, 10, 3),
                amount_minor=-300,
                currency="USD",
                description="starbucks manual",
                category_id=transport,
                manual_category=True,
                dedup_key="manual-1",
            )
        )
        s.commit()
    with Session(get_engine()) as s:
        s.add(Rule(user_id=uid, pattern="starbucks", category_id=groceries, position=0))
        s.commit()
    n = rules_service.reapply_uncategorized(Session(get_engine()), uid)
    assert n == 1  # only the uncategorized row was re-categorized
    with Session(get_engine()) as s:
        sys_t = s.exec(select(Transaction).where(Transaction.dedup_key == "sys-1")).first()
        assert sys_t.category_id == transport  # unchanged
        uncat_t = s.exec(select(Transaction).where(Transaction.dedup_key == "uncat-1")).first()
        assert uncat_t.category_id == groceries  # new
        manual_t = s.exec(select(Transaction).where(Transaction.dedup_key == "manual-1")).first()
        assert manual_t.category_id == transport  # unchanged (sticky)
