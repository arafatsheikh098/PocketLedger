"""Pagination boundaries for the transactions list."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _make_n_transactions(n: int) -> None:
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
        for i in range(n):
            day = (i % 28) + 1
            month = ((i // 28) % 12) + 1
            year = 2025 + (i // (28 * 12))
            s.add(
                Transaction(
                    user_id=u.id,
                    account_id=a.id,
                    date=date(year, month, day),
                    amount_minor=-(i + 1),
                    currency="USD",
                    description=f"Row {i}",
                    dedup_key=f"k{i}",
                )
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


def test_pagination_boundaries(client: TestClient) -> None:
    _make_n_transactions(60)
    _login(client)
    # PAGE_SIZE is 25. 60 rows => 3 pages: 25, 25, 10.
    # Rows are dated i=0..59 with increasing year+month+day, so date DESC
    # puts Row 59, Row 58, ... Row 35 on page 1.
    r = client.get("/transactions?page=1")
    assert "Row " in r.text
    page1 = sum(1 for i in range(60) if f"Row {i}" in r.text and i >= 35)
    assert page1 == 25
    r = client.get("/transactions?page=3")
    page3 = sum(1 for i in range(60) if f"Row {i}" in r.text and i < 10)
    assert page3 == 10
    # Out-of-range page clamps to the last page.
    r = client.get("/transactions?page=99")
    assert "Page 3 of 3" in r.text
