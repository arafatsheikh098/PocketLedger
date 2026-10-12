"""Backup + restore round-trip: counts and totals match.

We open a real on-disk SQLite file, populate it, back it up using
the same .backup command the script does, wipe the file, and
restore. The contents of the two files (after a refresh) must
match.
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.auth.passwords import hash_password
from app.models.account import Account
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories


def _have_sqlite3() -> bool:
    return shutil.which("sqlite3") is not None


@pytest.mark.skipif(not _have_sqlite3(), reason="sqlite3 CLI required")
def test_backup_and_restore_round_trip(tmp_path: Path) -> None:
    db_file = tmp_path / "pocket.db"
    backup_file = tmp_path / "backup.db"
    engine = create_engine(f"sqlite:///{db_file}")
    # Make sure tables exist.
    from app.models.account import Account as _A  # noqa
    from app.models.budget import Budget as _B  # noqa
    from app.models.category import Category as _C  # noqa
    from app.models.import_batch import ImportBatch as _I  # noqa
    from app.models.login_attempt import LoginAttempt as _L  # noqa
    from app.models.rule import Rule as _R  # noqa
    from app.models.transaction import Transaction as _T  # noqa
    from app.models.user import User as _U  # noqa

    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
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
        groceries = s.query(Category).filter(
            Category.user_id == u.id, Category.name == "Groceries"
        ).first()
        s.add(
            Transaction(
                user_id=u.id,
                account_id=a.id,
                date=datetime.date(2026, 10, 1),
                amount_minor=-1234,
                currency="USD",
                description="x",
                category_id=groceries.id,
                dedup_key="k1",
            )
        )
        s.commit()
    # Issue a WAL checkpoint so .backup captures everything in the main file.
    with Session(engine) as s:
        s.execute(__import__("sqlalchemy").text("PRAGMA wal_checkpoint(FULL)"))
        s.commit()
    # Back up.
    subprocess.run(
        ["sqlite3", str(db_file), f".backup '{backup_file}'"], check=True
    )
    assert backup_file.exists()
    # Snapshot counts and totals from the live DB.
    with Session(engine) as s:
        n_users = len(s.exec(__import__("sqlmodel").select(User)).all())
        n_txn = len(s.exec(__import__("sqlmodel").select(Transaction)).all())
        total_amount = sum(
            int(t.amount_minor) for t in s.exec(__import__("sqlmodel").select(Transaction)).all()
        )
    # Wipe and restore.
    db_file.unlink()
    assert not db_file.exists()
    shutil.copy(backup_file, db_file)
    engine2 = create_engine(f"sqlite:///{db_file}")
    with Session(engine2) as s:
        n_users2 = len(s.exec(__import__("sqlmodel").select(User)).all())
        n_txn2 = len(s.exec(__import__("sqlmodel").select(Transaction)).all())
        total_amount2 = sum(
            int(t.amount_minor)
            for t in s.exec(__import__("sqlmodel").select(Transaction)).all()
        )
    assert (n_users, n_txn, total_amount) == (n_users2, n_txn2, total_amount2)
