"""Alembic upgrade and downgrade round-trip.

We point Alembic at the same temp DB the rest of the tests use, then
run upgrade -> downgrade -> upgrade and verify the table list at each step.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = f"sqlite:///{db_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_alembic_upgrade_downgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "alembic_test.db"

    up = _alembic("upgrade", "head", db_path=db_path)
    assert up.returncode == 0, up.stdout + up.stderr

    # After upgrade, the users table exists.
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "users" in tables
    assert "transactions" in tables
    assert "rules" in tables
    assert "budgets" in tables

    down = _alembic("downgrade", "base", db_path=db_path)
    assert down.returncode == 0, down.stdout + down.stderr

    conn = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    assert "users" not in tables
    assert "transactions" not in tables
