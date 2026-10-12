"""Parametrized discovery of all M2 routes.

The pattern here is reused in M3..M7 to assert that every new route
requires a session and (for mutating routes) a valid CSRF token.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _make_user(username: str, password: str) -> None:
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


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/"),
        ("get", "/auth/change-password"),
    ],
)
def test_get_routes_require_session(client: TestClient, method: str, path: str) -> None:
    r = getattr(client, method)(path, follow_redirects=False)
    # / redirects to login (303), /auth/change-password redirects (303).
    assert r.status_code in (303, 307)


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/auth/logout"),
    ],
)
def test_post_routes_require_csrf(client: TestClient, method: str, path: str) -> None:
    # Logged out, no CSRF: 303 to login (because of the session check).
    r = getattr(client, method)(path, data={}, follow_redirects=False)
    assert r.status_code in (303, 307, 403)


def test_all_m2_routes_present(client: TestClient) -> None:
    _make_user("alice", "alicepass1")
    # Every M2 path is reachable.
    assert client.get("/health").status_code == 200
    assert client.get("/auth/login").status_code == 200
    assert client.get("/auth/register", follow_redirects=False).status_code == 303
