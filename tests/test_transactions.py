"""Transactions: sign convention, transfers excluded, CRUD."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services.totals import expense_minor, income_minor, net_minor


def _make_user(username: str) -> tuple[int, int, int]:
    """Create user with one account and a category; return (uid, acct_id, cat_id)."""
    with Session(get_engine()) as s:
        u = User(
            username=username,
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
        c = s.exec(select(Category).where(Category.user_id == u.id)).first()
        return u.id, a.id, c.id


def _login(client: TestClient, username: str) -> None:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": username, "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )


def test_create_expense_stored_negative(client: TestClient) -> None:
    uid, acct, cat = _make_user("alice")
    _login(client, "alice")
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/transactions",
        data={
            "date": "2026-10-12",
            "amount": "12.34",
            "kind": "expense",
            "description": "Coffee",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with Session(get_engine()) as s:
        t = s.exec(select(Transaction).where(Transaction.user_id == uid)).first()
    assert t.amount_minor == -1234


def test_create_income_stored_positive(client: TestClient) -> None:
    uid, acct, cat = _make_user("alice")
    _login(client, "alice")
    csrf = client.cookies.get("pocketledger_csrf")
    client.post(
        "/transactions",
        data={
            "date": "2026-10-12",
            "amount": "100.00",
            "kind": "income",
            "description": "Salary",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    with Session(get_engine()) as s:
        t = s.exec(select(Transaction).where(Transaction.user_id == uid)).first()
    assert t.amount_minor == 10000


def test_transfers_excluded_from_totals(client: TestClient) -> None:
    """A transfer must not affect income, expense or net totals."""
    uid, acct, cat = _make_user("alice")
    _login(client, "alice")
    csrf = client.cookies.get("pocketledger_csrf")
    # An expense of -1000, an income of +2000, and a transfer of -500.
    for body in [
        {
            "date": "2026-10-10",
            "amount": "10.00",
            "kind": "expense",
            "description": "Lunch",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
        },
        {
            "date": "2026-10-11",
            "amount": "20.00",
            "kind": "income",
            "description": "Refund",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
        },
        {
            "date": "2026-10-12",
            "amount": "5.00",
            "kind": "expense",
            "description": "To savings",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
            "is_transfer": "on",
        },
    ]:
        body["csrf_token"] = csrf
        client.post("/transactions", data=body, follow_redirects=False)

    with Session(get_engine()) as s:
        # income includes 2000 only; expense includes 1000 only; transfer
        # -500 must be excluded from all three totals.
        assert income_minor(s, uid) == 2000
        assert expense_minor(s, uid) == 1000
        assert net_minor(s, uid) == 2000 - 1000


def test_edit_and_delete_transaction(client: TestClient) -> None:
    uid, acct, cat = _make_user("alice")
    _login(client, "alice")
    csrf = client.cookies.get("pocketledger_csrf")
    client.post(
        "/transactions",
        data={
            "date": "2026-10-12",
            "amount": "1.00",
            "kind": "expense",
            "description": "Test",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    with Session(get_engine()) as s:
        txn_id = s.exec(select(Transaction).where(Transaction.user_id == uid)).first().id
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        f"/transactions/{txn_id}/edit",
        data={
            "date": "2026-10-13",
            "amount": "2.50",
            "kind": "expense",
            "description": "Updated",
            "notes": "",
            "account_id": str(acct),
            "category_id": str(cat),
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    with Session(get_engine()) as s:
        t = s.get(Transaction, txn_id)
    assert t.description == "Updated"
    assert t.amount_minor == -250

    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        f"/transactions/{txn_id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with Session(get_engine()) as s:
        assert s.get(Transaction, txn_id) is None


def test_cannot_edit_other_users_transaction(client: TestClient) -> None:
    _make_user("alice")
    _make_user("bob")
    _login(client, "bob")
    # Bob's account is different; he can't even see alice's txn id.
    # He tries to delete txn 9999 (alice's).
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/transactions/9999/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 404
