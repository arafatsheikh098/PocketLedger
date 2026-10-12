"""Dashboard: table fallback numbers equal the chart data attributes."""
from __future__ import annotations

import datetime
import json
import re

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories


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


def _login(client: TestClient) -> None:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf")
    client.post(
        "/auth/login",
        data={"username": "alice", "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )


def _table_amounts(html: str, table_id: str) -> list[int]:
    pat = re.compile(
        rf'<table id="{table_id}".*?</table>', re.DOTALL
    )
    m = pat.search(html)
    assert m is not None, f"table {table_id} not in HTML"
    block = m.group(0)
    return [int(am) for am in re.findall(r'data-amount-minor="(-?\d+)"', block)]


def _canvas_data(html: str, canvas_id: str, attr: str) -> list:
    pat = re.compile(
        rf'<canvas id="{canvas_id}"[^>]*?data-{attr}=\'([^\']+)\'', re.DOTALL
    )
    m = pat.search(html)
    assert m is not None, f"canvas {canvas_id} data-{attr} not in HTML"
    return json.loads(m.group(1))


def test_table_top_matches_canvas(client: TestClient) -> None:
    uid, acc = _setup()
    # Get current month.
    today = datetime.date.today()
    with Session(get_engine()) as s:
        groceries = s.exec(
            __import__("sqlmodel").select(Category).where(
                Category.user_id == uid, Category.name == "Groceries"
            )
        ).first()
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=today,
                amount_minor=-1234,
                currency="USD",
                description="x",
                category_id=groceries.id,
                dedup_key="d1",
            )
        )
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=today,
                amount_minor=-567,
                currency="USD",
                description="x",
                category_id=groceries.id,
                dedup_key="d2",
            )
        )
        s.commit()
    _login(client)
    r = client.get("/dashboard")
    assert r.status_code == 200
    html = r.text
    table_amounts = _table_amounts(html, "table-top")
    canvas_amounts = _canvas_data(html, "chart-top", "amounts")
    # The table rows + the canvas attribute should be the same numbers.
    assert sorted(table_amounts) == sorted(canvas_amounts)


def test_table_trend_matches_canvas(client: TestClient) -> None:
    uid, acc = _setup()
    today = datetime.date.today()
    with Session(get_engine()) as s:
        groceries = s.exec(
            __import__("sqlmodel").select(Category).where(
                Category.user_id == uid, Category.name == "Groceries"
            )
        ).first()
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=today,
                amount_minor=-1000,
                currency="USD",
                description="x",
                category_id=groceries.id,
                dedup_key="trend-1",
            )
        )
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=today,
                amount_minor=5000,
                currency="USD",
                description="salary",
                dedup_key="trend-2",
            )
        )
        s.commit()
    _login(client)
    r = client.get("/dashboard")
    assert r.status_code == 200
    html = r.text
    # The trend table has 6 rows. The last row's expense should match the canvas's last.
    trend_amounts = _table_amounts(html, "table-trend")
    # Each row contributes 2 numbers (income, expense). The 6th row's expense must
    # be the current month's.
    cur_expense = trend_amounts[-1]
    canvas_income = _canvas_data(html, "chart-trend", "income")
    canvas_expense = _canvas_data(html, "chart-trend-expense", "expense")
    assert cur_expense == canvas_expense[-1] == 1000
    assert canvas_income[-1] == 5000
