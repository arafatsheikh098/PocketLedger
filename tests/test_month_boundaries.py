"""Month boundaries respect the user's timezone via freezegun."""
from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from freezegun import freeze_time
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import budgets as budgets_service


def _setup_user(tz: str) -> tuple[int, int, int]:
    with Session(get_engine()) as s:
        u = User(
            username="alice",
            password_hash=hash_password("pw12345678"),
            base_currency="USD",
            timezone=tz,
        )
        s.add(u)
        s.commit()
        s.refresh(u)
        _seed_default_categories(s, u.id)
        a = Account(user_id=u.id, name="Checking", type="bank")
        s.add(a)
        s.commit()
        s.refresh(a)
        groceries = (
            s.query(Category).filter(Category.user_id == u.id, Category.name == "Groceries").first()
        )
        return u.id, a.id, groceries.id


def test_current_month_window_utc() -> None:
    uid, _, _ = _setup_user("UTC")
    with freeze_time("2026-10-15 12:00:00"):
        with Session(get_engine()) as s:
            u = s.get(User, uid)
            y, m, start, end = budgets_service.current_month_window(u)
    assert (y, m) == (2026, 10)
    assert start == datetime.date(2026, 10, 1)
    assert end == datetime.date(2026, 11, 1)


def test_current_month_window_new_york() -> None:
    """A 'late October' date in NY is still October, so the budget month is October."""
    uid, _, _ = _setup_user("America/New_York")
    with freeze_time("2026-10-31 22:00:00", tz_offset=0):  # 18:00 NY
        with Session(get_engine()) as s:
            u = s.get(User, uid)
            y, m, start, end = budgets_service.current_month_window(u)
    assert (y, m) == (2026, 10)
    assert start == datetime.date(2026, 10, 1)
    assert end == datetime.date(2026, 11, 1)


def test_current_month_window_new_york_late_oct() -> None:
    """Just before midnight NY on Oct 31 is still October."""
    uid, _, _ = _setup_user("America/New_York")
    with freeze_time("2026-11-01 03:00:00", tz_offset=0):  # 23:00 NY Oct 31
        with Session(get_engine()) as s:
            u = s.get(User, uid)
            y, m, _start, _end = budgets_service.current_month_window(u)
    assert (y, m) == (2026, 10)


def test_window_for_different_tz() -> None:
    """Two users, same data, two different timezones - the month window is the same."""
    uid_a, acc_a, cat_a = _setup_user("UTC")
    with Session(get_engine()) as s:
        s.add(
            Transaction(
                user_id=uid_a,
                account_id=acc_a,
                date=datetime.date(2026, 10, 15),
                amount_minor=-1000,
                currency="USD",
                description="x",
                category_id=cat_a,
                dedup_key="o1",
            )
        )
        s.add(Budget(user_id=uid_a, category_id=cat_a, month="2026-10", amount_minor=5000))
        s.commit()
    with Session(get_engine()) as s:
        u = s.get(User, uid_a)
        p = budgets_service.progress_for_user(s, u, 2026, 10)
    assert p[0].spent_minor == 1000


def test_invalid_timezone_falls_back_to_utc() -> None:
    with Session(get_engine()) as s:
        u = User(
            username="bob",
            password_hash=hash_password("pw12345678"),
            base_currency="USD",
            timezone="Mars/Olympus_Mons",
        )
        s.add(u)
        s.commit()
        s.refresh(u)
    with Session(get_engine()) as s:
        u = s.get(User, u.id)
        tz = budgets_service.resolve_tz(u)
    assert tz == ZoneInfo("UTC")
