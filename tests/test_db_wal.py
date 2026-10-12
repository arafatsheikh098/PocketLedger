from __future__ import annotations

import sqlite3

from app.db import db_file_path


def test_sqlite_wal_mode() -> None:
    path = db_file_path()
    assert path is not None
    assert path.exists()
    # WAL requires a connection to a file; the engine in get_engine has
    # already enabled it via the connect event, but verify with a fresh
    # connection because some test clients close the file.
    conn = sqlite3.connect(path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"
