"""Delete-account protection: an account with transactions is blocked."""
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


def test_delete_account_blocked_with_transactions(client: TestClient) -> None:
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
        s.add(
            Transaction(
                user_id=u.id,
                account_id=a.id,
                date=date(2026, 10, 1),
                amount_minor=-100,
                currency="USD",
                description="x",
                dedup_key="k1",
            )
        )
        s.commit()
        acct_id = a.id

    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        f"/accounts/{acct_id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # The redirect goes back to /accounts with an error about transactions.
    assert "transactions" in r.headers["location"].lower()
    # The account is still present.
    with Session(get_engine()) as s:
        assert s.get(Account, acct_id) is not None
