"""Auth flow: login, logout, change password, register, rate limit."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.user import User
from app.routers.auth import _seed_default_categories


@pytest.fixture
def make_user():
    def _make(username: str = "alice", password: str = "alicepass1") -> int:
        with Session(get_engine()) as s:
            user = User(
                username=username,
                password_hash=hash_password(password),
                base_currency="USD",
                timezone="UTC",
            )
            s.add(user)
            s.commit()
            s.refresh(user)
            _seed_default_categories(s, user.id)
            return user.id

    return _make


def test_login_logout_flow(client: TestClient, make_user) -> None:
    make_user("alice", "alicepass1")
    r = client.get("/auth/login")
    assert r.status_code == 200
    csrf = r.cookies.get("pocketledger_csrf")
    assert csrf

    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "alicepass1", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"

    # Follow the redirect: home page renders.
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "alice" in r.text

    # Logout: read the current CSRF from the cookie jar, not the response.
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/logout",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # After logout, home redirects to login.
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/login"


def test_login_bad_password(client: TestClient, make_user) -> None:
    make_user("alice", "alicepass1")
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "wrong", "csrf_token": csrf},
    )
    assert r.status_code == 200
    assert "invalid" in r.text.lower()


def test_change_password(client: TestClient, make_user) -> None:
    make_user("alice", "alicepass1")
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "alicepass1", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.get("/auth/change-password")
    assert r.status_code == 200
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/change-password",
        data={
            "current_password": "alicepass1",
            "new_password": "newpass99",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    # Old password rejected.
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "alicepass1", "csrf_token": csrf},
    )
    assert r.status_code == 200
    assert "invalid" in r.text.lower()
    # New password works.
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "newpass99", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_register_disabled_by_default(client: TestClient) -> None:
    r = client.get("/auth/register", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/login"


def test_register_when_allowed(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    from app import config as cfg

    cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    from app import create_app

    app = create_app()
    with TestClient(app) as c:
        r = c.get("/auth/register")
        assert r.status_code == 200
        csrf = r.cookies.get("pocketledger_csrf")
        r = c.post(
            "/auth/register",
            data={"username": "bob", "password": "bobpass99", "csrf_token": csrf},
            follow_redirects=False,
        )
        assert r.status_code == 303
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 200
        assert "bob" in r.text


def test_login_rate_limit(client: TestClient, make_user) -> None:
    make_user("alice", "alicepass1")
    for _ in range(5):
        r = client.get("/auth/login")
        csrf = r.cookies.get("pocketledger_csrf")
        r = client.post(
            "/auth/login",
            data={"username": "alice", "password": "wrong", "csrf_token": csrf},
        )
        assert r.status_code == 200
    # 6th attempt is locked out.
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    r = client.post(
        "/auth/login",
        data={"username": "alice", "password": "alicepass1", "csrf_token": csrf},
    )
    assert r.status_code == 200
    assert "too many" in r.text.lower()
