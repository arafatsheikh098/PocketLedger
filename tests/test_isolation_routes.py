"""Per-user isolation across M5 (rules) routes.

The list/create/delete/move operations on /rules/* are scoped to the
current user. The test exercises: user A creates a rule, user B
cannot see, edit, or delete it.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.category import Category
from app.models.rule import Rule
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


def _login_as(client: TestClient, username: str) -> str:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": username, "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    return client.cookies.get("pocketledger_csrf") or ""


def _first_category_id(user_id: int) -> int:
    with Session(get_engine()) as s:
        c = s.exec(
            select(Category).where(Category.user_id == user_id).order_by(Category.id)
        ).first()
        assert c is not None
        return c.id


def test_user_b_cannot_see_or_delete_user_a_rule(client: TestClient) -> None:
    a = _make_user("alice")
    _make_user("bob")
    with Session(get_engine()) as s:
        cat_a = _first_category_id(a)
        s.add(Rule(user_id=a, pattern="secret", category_id=cat_a, position=0))
        s.commit()
        rule_id = s.exec(select(Rule).where(Rule.user_id == a)).first().id
    # Bob logs in and visits /rules - he should not see Alice's rule.
    csrf = _login_as(client, "bob")
    r = client.get("/rules")
    assert r.status_code == 200
    assert "secret" not in r.text
    # Bob can't delete Alice's rule.
    r = client.post(
        f"/rules/{rule_id}/delete",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code in (303, 404)
    with Session(get_engine()) as s:
        rule = s.get(Rule, rule_id)
        assert rule is not None  # still exists
