"""Demo mode: banner, deterministic seeder, mount hook.

``DEMO_MODE=true`` turns on a banner on every page and ``SEED_ON_START=true``
seeds the database with 6 months of fake transactions the first time the
app starts. The seed is deterministic (a fixed PRNG) so the demo data
looks the same on every cold start.
"""
from __future__ import annotations

import datetime as _dt
import random

from sqlmodel import Session, select

from .auth.passwords import hash_password
from .models.account import Account
from .models.budget import Budget
from .models.category import Category
from .models.transaction import Transaction
from .models.user import User
from .routers.auth import _seed_default_categories

_DEMO_USERNAME = "demo"
_DEMO_PASSWORD = "demo1234"
_DEMO_CURRENCY = "USD"
_DEMO_TIMEZONE = "UTC"

_DEMO_DESCRIPTIONS: list[tuple[str, int, str]] = [
    # (description, amount_minor, category_name)
    ("Starbucks", -475, "Restaurants"),
    ("Whole Foods", -7820, "Groceries"),
    ("Uber", -1850, "Transport"),
    ("Spotify", -999, "Entertainment"),
    ("Comcast", -7500, "Utilities"),
    ("Rent", -180000, "Rent"),
    ("Acme Corp Payroll", 250000, "Income"),
    ("Trader Joe's", -3215, "Groceries"),
    ("Shell Gas", -4400, "Transport"),
    ("Netflix", -1599, "Entertainment"),
]


def ensure_demo_user(session: Session) -> User:
    """Idempotently create the demo user + account + categories."""
    user = session.exec(select(User).where(User.username == _DEMO_USERNAME)).first()
    if user is not None:
        return user
    user = User(
        username=_DEMO_USERNAME,
        password_hash=hash_password(_DEMO_PASSWORD),
        base_currency=_DEMO_CURRENCY,
        timezone=_DEMO_TIMEZONE,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    _seed_default_categories(session, user.id)
    account = Account(user_id=user.id, name="Demo Checking", type="bank")
    session.add(account)
    session.commit()
    session.refresh(account)
    return user


def seed_demo_data(session: Session, user: User, *, today: _dt.date | None = None) -> int:
    """Seed 6 months of transactions, one budget, deterministic.

    Returns the number of transactions inserted.
    """
    if today is None:
        today = _dt.date.today()
    # Idempotency: don't re-seed if there are already any txns.
    has_any = session.exec(
        select(Transaction).where(Transaction.user_id == user.id)
    ).first()
    if has_any is not None:
        return 0
    # Deterministic seed.
    rng = random.Random("pocketledger-demo-seed-v1")
    account = session.exec(
        select(Account).where(Account.user_id == user.id).order_by(Account.id)
    ).first()
    assert account is not None
    categories = list(
        session.exec(select(Category).where(Category.user_id == user.id)).all()
    )
    cat_by_name = {c.name: c.id for c in categories}
    inserted = 0
    for month_offset in range(6):
        # Start of the month, minus month_offset.
        year = today.year
        month = today.month - month_offset
        while month <= 0:
            month += 12
            year -= 1
        # 8-15 transactions per month.
        n = rng.randint(8, 15)
        for _ in range(n):
            desc, amt, cat_name = rng.choice(_DEMO_DESCRIPTIONS)
            day = rng.randint(1, 28)
            d = _dt.date(year, month, day)
            cat_id = cat_by_name.get(cat_name)
            session.add(
                Transaction(
                    user_id=user.id,
                    account_id=account.id,
                    date=d,
                    amount_minor=amt,
                    currency=user.base_currency,
                    description=desc,
                    category_id=cat_id,
                    dedup_key=f"demo-{d.isoformat()}-{desc}-{rng.randint(0, 1_000_000)}",
                )
            )
            inserted += 1
    # One budget that is over 80% spent (warning), so the dashboard banner shows.
    groceries = cat_by_name.get("Groceries")
    if groceries is not None:
        month_str = f"{today.year:04d}-{today.month:02d}"
        existing_b = session.exec(
            select(Budget)
            .where(Budget.user_id == user.id)
            .where(Budget.category_id == groceries)
            .where(Budget.month == month_str)
        ).first()
        if existing_b is None:
            session.add(
                Budget(
                    user_id=user.id,
                    category_id=groceries,
                    month=month_str,
                    amount_minor=10000,  # $100
                )
            )
    session.commit()
    return inserted


def banner_html() -> str:
    """The HTML markup for the demo banner. Empty when demo is off."""
    return (
        '<div class="banner banner-demo">'
        "DEMO MODE - this PocketLedger instance is public. "
        "Do not enter real financial data."
        "</div>"
    )
