"""Database engine, session factory, and per-request dependency.

The app uses SQLite in WAL mode for concurrency-friendly reads.
"""
from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings, sqlite_file_path

_engine: Engine | None = None


def _ensure_sqlite_dir(url: str) -> None:
    if url.startswith("sqlite"):
        path = sqlite_file_path(url)
        parent = path.parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    settings = get_settings()
    url = settings.database_url
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        url = test_url
    _ensure_sqlite_dir(url)
    connect_args = {"check_same_thread": False}
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _set_sqlite_pragmas)
    _engine = engine
    return engine


def reset_engine_for_tests() -> None:
    """Drop the cached engine. Tests use this to point at a temp DB."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def create_db_and_tables() -> None:
    engine = get_engine()
    # Import models so they register with SQLModel.metadata.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    engine = get_engine()
    with Session(engine, expire_on_commit=False) as session:
        yield session


def db_file_path() -> Path | None:
    settings = get_settings()
    url = os.environ.get("TEST_DATABASE_URL") or settings.database_url
    if url.startswith("sqlite"):
        return sqlite_file_path(url)
    return None
