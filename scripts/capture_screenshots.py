"""Capture the screenshots used in README.md.

This boots a real uvicorn on a free port, logs in as the demo user
(``SEED_ON_START=true DEMO_MODE=true``), and writes a small set of
PNG screenshots to ``docs/screenshots/``:

- ``login.png``        — /auth/login with the demo banner
- ``dashboard.png``    — /dashboard with the 6-month trend + budget progress
- ``transactions.png`` — /transactions list view

The script is part of the dev tooling, not the test suite. Run it
locally with:

    SEED_ON_START=true DEMO_MODE=true ALLOW_REGISTRATION=false \\
        DATABASE_URL=sqlite:///pocketledger_shots.db \\
        .venv/bin/python -c \\
        "from app.db import create_db_and_tables; \\
         create_db_and_tables(); \\
         from sqlmodel import Session; from app.db import get_engine; \\
         from app.demo import ensure_demo_user, seed_demo_data; \\
         s = Session(get_engine()); \\
         u = ensure_demo_user(s); \\
         seed_demo_data(s, u)"

    DATABASE_URL=sqlite:///pocketledger_shots.db \\
        .venv/bin/python scripts/capture_screenshots.py
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request
from contextlib import closing
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for_server(url: str, timeout: float = 5.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError(f"server at {url} did not start")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    from app import create_app

    port = free_port()
    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{port}"
    try:
        wait_for_server(base + "/health")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            # 1. Login page (banner visible)
            page.goto(base + "/auth/login")
            page.screenshot(path=str(OUT / "login.png"), full_page=True)
            # 2. Log in as demo
            csrf = next(
                c["value"]
                for c in page.context.cookies(base + "/auth/login")
                if c["name"] == "pocketledger_csrf"
            )
            page.fill('input[name="username"]', "demo")
            page.fill('input[name="password"]', "demo1234")
            page.evaluate(
                f"document.querySelector('input[name=\"csrf_token\"]').value = {csrf!r}"
            )
            page.click('button[type="submit"]')
            page.wait_for_url(base + "/")
            # 3. Dashboard
            page.goto(base + "/dashboard")
            page.wait_for_selector("#table-progress")
            page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)
            # 4. Transactions
            page.goto(base + "/transactions")
            page.wait_for_load_state("networkidle")
            page.screenshot(path=str(OUT / "transactions.png"), full_page=True)
            browser.close()
    finally:
        server.should_exit = True
        t.join(timeout=2)
    for f in ("login.png", "dashboard.png", "transactions.png"):
        path = OUT / f
        if not path.exists() or path.stat().st_size < 1000:
            print(f"FAIL: {f} missing or too small", file=sys.stderr)
            return 1
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
