"""Playwright: dashboard chart renders and screenshot is non-empty.

Skipped if a browser isn't installed; install with:
    .venv/bin/playwright install chromium
"""
from __future__ import annotations

import datetime
import os
import socket
import threading
import time
import urllib.request
from contextlib import closing

import uvicorn
from sqlmodel import Session, select

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories


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


def test_dashboard_chart_renders(page, tmp_path) -> None:
    """End-to-end: log in via a real HTTP server, view dashboard, take screenshot."""
    uid, acc = _setup()
    today = datetime.date.today()
    with Session(get_engine()) as s:
        groceries = s.exec(
            select(Category).where(Category.user_id == uid, Category.name == "Groceries")
        ).first()
        s.add(
            Transaction(
                user_id=uid,
                account_id=acc,
                date=today,
                amount_minor=-2500,
                currency="USD",
                description="x",
                category_id=groceries.id,
                dedup_key="p1",
            )
        )
        s.commit()
    # Boot a real uvicorn server in a thread on a free port.
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
        # Log in via Playwright.
        page.goto(base + "/auth/login")
        csrf_cookie = page.context.cookies(base + "/auth/login")
        csrf_value = next(c["value"] for c in csrf_cookie if c["name"] == "pocketledger_csrf")
        # Submit login. The CSRF input is hidden; set it via JS.
        page.fill('input[name="username"]', "alice")
        page.fill('input[name="password"]', "pw12345678")
        page.evaluate(
            f"document.querySelector('input[name=\"csrf_token\"]').value = {csrf_value!r}"
        )
        page.click('button[type="submit"]')
        page.wait_for_url(base + "/")
        # Visit dashboard.
        page.goto(base + "/dashboard")
        page.wait_for_selector("#chart-top")
        page.wait_for_function("document.querySelector('#chart-top')?.width > 0")
        screenshot_path = tmp_path / "dashboard.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        size = os.path.getsize(screenshot_path)
        assert size > 1000, f"screenshot is suspiciously small: {size} bytes"
    finally:
        server.should_exit = True
        t.join(timeout=2)
