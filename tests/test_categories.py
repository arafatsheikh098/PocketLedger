"""Categories: default seeding, CRUD, default protection."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.category import DEFAULT_CATEGORIES, Category
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _make_user(username: str) -> int:
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
        return u.id


def test_default_categories_seeded() -> None:
    uid = _make_user("alice")
    with Session(get_engine()) as s:
        names = [c.name for c in s.exec(select(Category).where(Category.user_id == uid)).all()]
    for d in DEFAULT_CATEGORIES:
        assert d in names


def test_create_and_delete_custom_category(client: TestClient) -> None:
    _make_user("alice")
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        "/categories",
        data={"name": "Coffee", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with Session(get_engine()) as s:
        c = s.exec(select(Category).where(Category.name == "Coffee")).first()
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        f"/categories/{c.id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303


def test_cannot_delete_default_category(client: TestClient) -> None:
    _make_user("alice")
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    with Session(get_engine()) as s:
        c = s.exec(select(Category).where(Category.is_default == True)).first()  # noqa: E712
    csrf = client.cookies.get("pocketledger_csrf")
    r = client.post(
        f"/categories/{c.id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "default" in (r.headers.get("location") or "").lower()
