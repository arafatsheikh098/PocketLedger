"""Accounts CRUD: list, create, rename, delete, and per-user isolation."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _make_user_with_account(username: str, password: str = "pw12345678") -> int:
    with Session(get_engine()) as s:
        u = User(
            username=username,
            password_hash=hash_password(password),
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
        return u.id


def _login(client: TestClient, username: str, password: str = "pw12345678") -> None:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


def test_accounts_list_requires_login(client: TestClient) -> None:
    r = client.get("/accounts", follow_redirects=False)
    assert r.status_code in (303, 307)


def test_create_account(client: TestClient) -> None:
    _make_user_with_account("alice")
    _login(client, "alice")
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/accounts",
        data={"name": "Savings", "type": "bank", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.get("/accounts")
    assert r.status_code == 200
    assert "Savings" in r.text


def test_invalid_account_type_rejected(client: TestClient) -> None:
    _make_user_with_account("alice")
    _login(client, "alice")
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/accounts",
        data={"name": "X", "type": "nope", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "invalid" in r.headers["location"].lower()
    assert "account" in r.headers["location"].lower()


def test_delete_empty_account(client: TestClient) -> None:
    _make_user_with_account("alice")
    _login(client, "alice")
    with Session(get_engine()) as s:
        acct_id = s.exec(
            __import__("sqlmodel").select(Account).where(Account.name == "Checking")
        ).first().id
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(f"/accounts/{acct_id}/delete", data={"csrf_token": csrf}, follow_redirects=False)
    assert r.status_code == 303


def test_user_cannot_delete_other_users_account(client: TestClient) -> None:
    _make_user_with_account("alice")
    _make_user_with_account("bob")
    _login(client, "bob")
    with Session(get_engine()) as s:
        alice_user = s.exec(select(User).where(User.username == "alice")).first()
        alice_acct_id = s.exec(
            select(Account).where(Account.user_id == alice_user.id)
        ).first().id
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        f"/accounts/{alice_acct_id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    # Bob can't even see it; the row is not his.
    assert r.status_code == 404
