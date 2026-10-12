"""Rule matching is case-insensitive and ignores leading/trailing whitespace."""
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
        return u.id


def _cat_id(name: str) -> int:
    with Session(get_engine()) as s:
        c = s.exec(select(Category).where(Category.name == name)).first()
        assert c is not None
        return c.id


def test_case_insensitive_match() -> None:
    uid = _setup()
    cat = _cat_id("Groceries")
    rule = Rule(user_id=uid, pattern="StarBucks", category_id=cat, position=0)
    assert rules_service.apply_to_description("STARBUCKS #123", [rule]) == cat
    assert rules_service.apply_to_description("starbucks", [rule]) == cat
    assert rules_service.apply_to_description("StArBuCkS Coffee", [rule]) == cat


def test_trim_whitespace() -> None:
    uid = _setup()
    cat = _cat_id("Groceries")
    rule = Rule(user_id=uid, pattern="  starbucks  ", category_id=cat, position=0)
    assert rules_service.apply_to_description("starbucks #1", [rule]) == cat
    assert rules_service.apply_to_description("STARBUCKS", [rule]) == cat


def test_empty_description_no_match() -> None:
    uid = _setup()
    cat = _cat_id("Groceries")
    rule = Rule(user_id=uid, pattern="starbucks", category_id=cat, position=0)
    assert rules_service.apply_to_description("", [rule]) is None
    assert rules_service.apply_to_description("   ", [rule]) is None
