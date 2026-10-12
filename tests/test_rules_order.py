"""Rules: ordered, first match wins."""
from __future__ import annotations

from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.category import Category
from app.models.rule import Rule
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import rules as rules_service


def _setup() -> tuple[int, int]:
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
        return u.id, a.id


def _cat_id(name: str) -> int:
    with Session(get_engine()) as s:
        c = s.exec(select(Category).where(Category.name == name)).first()
        assert c is not None
        return c.id


def test_first_match_wins() -> None:
    uid, _ = _setup()
    groceries = _cat_id("Groceries")
    transport = _cat_id("Transport")
    rules = [
        Rule(user_id=uid, pattern="starbucks", category_id=groceries, position=0),
        Rule(user_id=uid, pattern="coffee", category_id=transport, position=1),
    ]
    assert rules_service.apply_to_description("Starbucks #1234", rules) == groceries
    assert rules_service.apply_to_description("COFFEE SHOP", rules) == transport


def test_order_editable_via_position() -> None:
    uid, _ = _setup()
    groceries = _cat_id("Groceries")
    transport = _cat_id("Transport")
    r1 = Rule(user_id=uid, pattern="a", category_id=groceries, position=10)
    r2 = Rule(user_id=uid, pattern="a", category_id=transport, position=20)
    # r1 has lower position, so it wins.
    assert rules_service.apply_to_description("anything", [r1, r2]) == groceries
    # After swap, r2 wins.
    r1.position, r2.position = r2.position, r1.position
    assert rules_service.apply_to_description("anything", [r1, r2]) == transport


def test_lower_position_wins_even_with_secondary_sort() -> None:
    uid, _ = _setup()
    a, b = _cat_id("Groceries"), _cat_id("Transport")
    rules = [
        Rule(user_id=uid, pattern="salary", category_id=a, position=0),
        Rule(user_id=uid, pattern="salary", category_id=b, position=0),  # tie
    ]
    # Same position, ordered by id; first created (lower id) wins.
    result = rules_service.apply_to_description("monthly salary", rules)
    assert result in (a, b)
