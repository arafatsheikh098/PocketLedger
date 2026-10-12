"""Filter matrix: combine date range, account, category, text, uncategorized."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _seed_three_transactions() -> None:
    """Three transactions across two categories and two dates, one uncategorized."""
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
        cats = s.exec(select(Category).where(Category.user_id == u.id)).all()
        cat_groceries = next(c for c in cats if c.name == "Groceries")
        cat_salary = next(c for c in cats if c.name == "Salary")

        s.add_all(
            [
                Transaction(
                    user_id=u.id,
                    account_id=a.id,
                    date=date(2026, 10, 1),
                    amount_minor=-1500,
                    currency="USD",
                    description="Whole Foods",
                    category_id=cat_groceries.id,
                    dedup_key="k1",
                ),
                Transaction(
                    user_id=u.id,
                    account_id=a.id,
                    date=date(2026, 10, 15),
                    amount_minor=50000,
                    currency="USD",
                    description="Paycheck",
                    category_id=cat_salary.id,
                    dedup_key="k2",
                ),
                Transaction(
                    user_id=u.id,
                    account_id=a.id,
                    date=date(2026, 10, 20),
                    amount_minor=-999,
                    currency="USD",
                    description="Mystery",
                    category_id=None,
                    dedup_key="k3",
                ),
            ]
        )
        s.commit()


def _login(client: TestClient) -> None:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )


def test_filter_by_text(client: TestClient) -> None:
    _seed_three_transactions()
    _login(client)
    r = client.get("/transactions?text=whole")
    assert "Whole Foods" in r.text
    assert "Mystery" not in r.text


def test_filter_uncategorized_only(client: TestClient) -> None:
    _seed_three_transactions()
    _login(client)
    r = client.get("/transactions?only_uncategorized=true")
    assert "Mystery" in r.text
    assert "Whole Foods" not in r.text
    assert "Paycheck" not in r.text


def test_filter_date_range(client: TestClient) -> None:
    _seed_three_transactions()
    _login(client)
    r = client.get("/transactions?date_from=2026-10-10&date_to=2026-10-31")
    assert "Whole Foods" not in r.text
    assert "Paycheck" in r.text
    assert "Mystery" in r.text


def test_filter_category(client: TestClient) -> None:
    _seed_three_transactions()
    _login(client)
    r = client.get("/transactions?only_uncategorized=false")
    with Session(get_engine()) as s:
        u = s.exec(select(User).where(User.username == "alice")).first()
        cat = s.exec(
            select(Category).where(Category.user_id == u.id, Category.name == "Groceries")
        ).first()
    r = client.get(f"/transactions?category_id={cat.id}")
    assert "Whole Foods" in r.text
    assert "Paycheck" not in r.text
    assert "Mystery" not in r.text


def test_filter_combined(client: TestClient) -> None:
    _seed_three_transactions()
    _login(client)
    with Session(get_engine()) as s:
        u = s.exec(select(User).where(User.username == "alice")).first()
        cat = s.exec(
            select(Category).where(Category.user_id == u.id, Category.name == "Groceries")
        ).first()
    r = client.get(
        f"/transactions?date_from=2026-10-01&date_to=2026-10-05&category_id={cat.id}"
    )
    assert "Whole Foods" in r.text
    assert "Paycheck" not in r.text
    assert "Mystery" not in r.text
