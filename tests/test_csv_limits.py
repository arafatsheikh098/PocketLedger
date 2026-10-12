"""Oversize and non-CSV uploads are rejected safely."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _login(client: TestClient, uid: int) -> None:
    pass  # login helper is in test_csv_limits integration


def _setup() -> int:
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
        return a.id


def test_oversize_rejected(client: TestClient) -> None:
    account_id = _setup()
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    csrf = client.cookies.get("pocketledger_csrf")
    big = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post(
        "/imports/upload",
        data={"account_id": str(account_id), "csrf_token": csrf},
        files={"file": ("big.csv", big, "text/csv")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "too%20large" in r.headers["location"].lower() or "too+large" in r.headers["location"].lower()


def test_non_csv_extension_rejected(client: TestClient) -> None:
    account_id = _setup()
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/imports/upload",
        data={"account_id": str(account_id), "csrf_token": csrf},
        files={"file": ("x.exe", b"MZ\x00\x00", "application/octet-stream")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "only" in r.headers["location"].lower()
    assert ".csv" in r.headers["location"].lower()
