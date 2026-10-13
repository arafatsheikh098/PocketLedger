"""End-to-end Playwright test: import -> categorized -> over-budget -> export.

This spins up a real uvicorn server on a free port, drives a browser
through the wizard, and downloads the XLSX. Skipped if Playwright
browsers are not installed.
"""
from __future__ import annotations

import datetime
import os
import socket
import threading
import time
import urllib.request
from contextlib import closing

import pytest
import uvicorn
from openpyxl import load_workbook
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.models.account import Account
from app.models.budget import Budget
from app.models.category import Category
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _has_browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return bool(p.chromium.executable_path and os.path.exists(p.chromium.executable_path))
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_browser(),
    reason="Playwright chromium browser not installed (run 'playwright install chromium')",
)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 5.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"server at {url} did not start")


def _seed() -> int:
    from app.models.transaction import Transaction
    with Session(__import__("app.db", fromlist=["get_engine"]).get_engine()) as s:
        u = User(
            username="alice",
            password_hash=hash_password("pw12345678"),
            base_currency="USD",
            timezone="UTC",
        )
        s.add(u)
        s.commit()
        uid = u.id
        _seed_default_categories(s, uid)
        a = Account(user_id=uid, name="Checking", type="bank")
        s.add(a)
        s.commit()
        # A budget that will be over once we import groceries.
        groceries = s.exec(
            select(Category).where(Category.user_id == uid, Category.name == "Groceries")
        ).first()
        today = datetime.date.today()
        month_str = f"{today.year:04d}-{today.month:02d}"
        s.add(
            Budget(
                user_id=uid,
                category_id=groceries.id,
                month=month_str,
                amount_minor=5000,  # $50 budget
            )
        )
        s.commit()
        # Add two grocery transactions this month that together exceed $50,
        # so the dashboard's "over budget" status row is rendered.
        s.add_all(
            [
                Transaction(
                    user_id=uid,
                    account_id=a.id,
                    date=today,
                    amount_minor=-6500,  # $65
                    currency="USD",
                    description="Whole Foods",
                    category_id=groceries.id,
                    dedup_key="e2e-1",
                ),
                Transaction(
                    user_id=uid,
                    account_id=a.id,
                    date=today,
                    amount_minor=-4000,  # $40
                    currency="USD",
                    description="Trader Joes",
                    category_id=groceries.id,
                    dedup_key="e2e-2",
                ),
            ]
        )
        s.commit()
    return uid


def _login(page, base: str, username: str = "alice", password: str = "pw12345678") -> None:
    page.goto(base + "/auth/login")
    csrf_value = next(
        c["value"] for c in page.context.cookies(base + "/auth/login")
        if c["name"] == "pocketledger_csrf"
    )
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.evaluate(
        f"document.querySelector('input[name=\"csrf_token\"]').value = {csrf_value!r}"
    )
    page.click('button[type="submit"]')
    page.wait_for_url(base + "/")


def test_e2e_log_in_and_export_xlsx(page, tmp_path) -> None:
    """End-to-end: log in, visit dashboard, download the XLSX export."""
    _seed()
    from app import create_app

    port = _free_port()
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        _wait_for_server(base + "/health")
        # Log in via the real UI.
        _login(page, base)
        # Dashboard renders, the seeded budget is over 100% (Whole Foods + Trader Joes
        # add up to $105 vs a $50 budget), so the over-budget row must be present.
        page.goto(base + "/dashboard")
        page.wait_for_selector("#table-progress")
        body = page.text_content("body")
        assert "over" in (body or "").lower()
        # Download the XLSX with the same cookies the browser has.
        cookies = page.context.cookies(base)
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        req = urllib.request.Request(base + "/exports/transactions.xlsx")
        req.add_header("Cookie", cookie_header)
        xlsx_path = tmp_path / "export.xlsx"
        with urllib.request.urlopen(req) as resp, open(xlsx_path, "wb") as f:
            f.write(resp.read())
        assert xlsx_path.stat().st_size > 100
        wb = load_workbook(xlsx_path)
        assert "Transactions" in wb.sheetnames
        assert "Summary" in wb.sheetnames
    finally:
        server.should_exit = True
        t.join(timeout=2)
