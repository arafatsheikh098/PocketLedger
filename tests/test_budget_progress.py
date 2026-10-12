"""Budget progress: integer sums match a hand-worked example."""
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
    """Create user with one account. Returns (user_id, account_id, groceries_id)."""
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


def _add_txn(s: Session, uid: int, acc: int, date_: datetime.date, amt_minor: int, cat: int | None) -> None:
    s.add(
        Transaction(
            user_id=uid,
            account_id=acc,
            date=date_,
            amount_minor=amt_minor,
            currency="USD",
            description="x",
            category_id=cat,
            dedup_key=f"k-{date_}-{amt_minor}-{cat}",
        )
    )
    s.commit()


def test_hand_worked_progress() -> None:
    """Three groceries purchases adding up to $42.00 against a $60.00 budget = 70%."""
    uid, acc, groceries = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=groceries, month="2026-10", amount_minor=6000))
        s.commit()
    with Session(get_engine()) as s:
        _add_txn(s, uid, acc, datetime.date(2026, 10, 1), -1500, groceries)
        _add_txn(s, uid, acc, datetime.date(2026, 10, 5), -1200, groceries)
        _add_txn(s, uid, acc, datetime.date(2026, 10, 20), -1500, groceries)
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        progress = budgets_service.progress_for_user(s, u, 2026, 10)
    assert len(progress) == 1
    p = progress[0]
    assert p.spent_minor == 4200  # 1500 + 1200 + 1500
    assert p.budget.amount_minor == 6000
    assert p.pct == 70  # 4200/6000 = 70
    assert p.status == "ok"  # 70% < 80%


def test_transfers_excluded_from_spent() -> None:
    uid, acc, groceries = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=groceries, month="2026-10", amount_minor=10000))
        s.commit()
    with Session(get_engine()) as s:
        _add_txn(s, uid, acc, datetime.date(2026, 10, 3), -5000, groceries)  # groceries
        # a transfer for the same amount and same category - must be excluded
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=datetime.date(2026, 10, 3),
                amount_minor=-5000,
                currency="USD",
                description="transfer",
                category_id=groceries,
                is_transfer=True,
                dedup_key="tfer-1",
            )
        )
        s.commit()
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        progress = budgets_service.progress_for_user(s, u, 2026, 10)
    assert progress[0].spent_minor == 5000  # transfer excluded


def test_income_excluded_from_spent() -> None:
    uid, acc, groceries = _setup()
    with Session(get_engine()) as s:
        s.add(Budget(user_id=uid, category_id=groceries, month="2026-10", amount_minor=10000))
        s.commit()
    with Session(get_engine()) as s:
        # positive amount in the groceries category (refund) - not counted as spent
        _add_txn(s, uid, acc, datetime.date(2026, 10, 3), 5000, groceries)
    with Session(get_engine()) as s:
        u = s.get(User, uid)
        progress = budgets_service.progress_for_user(s, u, 2026, 10)
    assert progress[0].spent_minor == 0
    assert progress[0].pct == 0
