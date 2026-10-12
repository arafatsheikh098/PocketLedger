"""Budget thresholds: 80% warning, 100% over, exact boundaries."""
from __future__ import annotations

import datetime

from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import budgets as budgets_service


def _setup() -> tuple[int, int, int]:
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
        groceries = s.exec(
            select(Category).where(Category.user_id == u.id, Category.name == "Groceries")
        ).first()
        assert groceries is not None
        return u.id, a.id, groceries.id


def _seed_spent(uid: int, acc: int, cat: int, amount_minor: int) -> None:
    with Session(get_engine()) as s:
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=datetime.date(2026, 10, 3),
                amount_minor=-amount_minor,
                currency="USD",
                description="x",
                category_id=cat,
                dedup_key=f"k-{amount_minor}",
            )
        )
        s.commit()


def test_just_below_80_pct_is_ok() -> None:
    uid, acc, cat = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=cat, month="2026-10", amount_minor=10000))
        s.commit()
    _seed_spent(uid, acc, cat, 7999)  # 79.99%
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        p = budgets_service.progress_for_user(s, u, 2026, 10)[0]
    assert p.pct == 79
    assert p.status == "ok"


def test_80_pct_is_warning() -> None:
    uid, acc, cat = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=cat, month="2026-10", amount_minor=10000))
        s.commit()
    _seed_spent(uid, acc, cat, 8000)  # exactly 80%
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        p = budgets_service.progress_for_user(s, u, 2026, 10)[0]
    assert p.pct == 80
    assert p.status == "warning"


def test_99_pct_is_warning() -> None:
    uid, acc, cat = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=cat, month="2026-10", amount_minor=10000))
        s.commit()
    _seed_spent(uid, acc, cat, 9999)  # 99.99%
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        p = budgets_service.progress_for_user(s, u, 2026, 10)[0]
    assert p.pct == 99
    assert p.status == "warning"


def test_100_pct_is_over() -> None:
    uid, acc, cat = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=cat, month="2026-10", amount_minor=10000))
        s.commit()
    _seed_spent(uid, acc, cat, 10000)  # exactly 100%
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        p = budgets_service.progress_for_user(s, u, 2026, 10)[0]
    assert p.pct == 100
    assert p.status == "over"


def test_over_100_pct_is_over() -> None:
    uid, acc, cat = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=cat, month="2026-10", amount_minor=10000))
        s.commit()
    _seed_spent(uid, acc, cat, 15000)
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        p = budgets_service.progress_for_user(s, u, 2026, 10)[0]
    assert p.pct == 150
    assert p.status == "over"
    assert p.remaining_minor < 0
