"""Pytest fixtures.

Every test gets a fresh on-disk SQLite database in a temp dir, so the
tests exercise real SQLite behavior (WAL pragmas, transactions).
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Each test session sets a unique database file before importing the app.
_TMP_DIR = Path(os.environ.get("PYTEST_TMP_DIR", "/tmp/pocketledger-tests"))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("TEST_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-for-tests-only-do-not-use-in-prod")
    monkeypatch.setenv("ALLOW_REGISTRATION", "false")
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("SEED_ON_START", "false")
    monkeypatch.setenv("APP_ENV", "development")

    # Reset cached engine and reload db module so each test gets a clean slate.
    from app import db as db_module
    importlib.reload(db_module)
    db_module.reset_engine_for_tests()
    db_module.create_db_and_tables()
    yield
    db_module.reset_engine_for_tests()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    from app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c
