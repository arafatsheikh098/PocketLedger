"""CSRF protection on state-changing routes."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _login(client: TestClient, username: str, password: str) -> None:
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

    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        follow_redirects=False,
    )


def test_logout_without_csrf_rejected(client: TestClient) -> None:
    _login(client, "alice", "alicepass1")
    r = client.post("/auth/logout", data={})
    assert r.status_code == 403


def test_logout_with_wrong_csrf_rejected(client: TestClient) -> None:
    _login(client, "alice", "alicepass1")
    r = client.post(
        "/auth/logout",
        data={"csrf_token": "not-the-real-token"},
    )
    assert r.status_code == 403
