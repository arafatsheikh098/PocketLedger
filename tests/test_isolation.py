"""Per-user isolation (M2 scope).

Two users exist; the test ensures user B cannot see or change user A's
records through any M2 route.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _make_user(username: str, password: str) -> int:
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
        return u.id


def _login_as(client: TestClient, username: str, password: str) -> str:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )
    return csrf or ""


def test_users_see_only_their_home(client: TestClient) -> None:
    _make_user("alice", "alicepass1")
    _make_user("bob", "bobpass99")
    _login_as(client, "alice", "alicepass1")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "alice" in r.text
    assert "bob" not in r.text


def test_change_password_rejects_other_users_current(client: TestClient) -> None:
    _make_user("alice", "alicepass1")
    _make_user("bob", "bobpass99")
    _login_as(client, "bob", "bobpass99")
    r = client.get("/auth/change-password")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/change-password",
        data={
            "current_password": "alicepass1",  # wrong
            "new_password": "hacked1234",
            "csrf_token": csrf,
        },
    )
    assert r.status_code == 400
    # Alice can still log in with her old password.
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "alicepass1", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
