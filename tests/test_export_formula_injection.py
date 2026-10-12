"""Formula-injection neutralization in CSV/XLSX cells."""
from __future__ import annotations

import datetime
import io

from openpyxl import load_workbook
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.services import exports as exports_service


def _setup_with_malicious() -> int:
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
        # Various formula-injection attempts.
        bad = [
            ("=cmd|'/c calc'!A1", "k1"),
            ("+1+1", "k2"),
            ("@SUM(1+1)", "k3"),
            ("-2+3", "k4"),
            ("\tmalicious", "k5"),  # tab prefix
            ("\rmalicious", "k6"),  # CR prefix
            ("normal", "k7"),  # benign, must pass through
            ("=HYPERLINK(\"evil\",\"x\")", "k8"),
        ]
        for desc, dk in bad:
            s.add(
                Transaction(
                    user_id=u.id,
                    account_id=a.id,
                    date=datetime.date(2026, 10, 1),
                    amount_minor=-100,
                    currency="USD",
                    description=desc,
                    dedup_key=dk,
                )
            )
        s.commit()
        return u.id


def test_sanitize_helper() -> None:
    assert exports_service.sanitize("=evil()") == "'=evil()"
    assert exports_service.sanitize("+1+1") == "'+1+1"
    assert exports_service.sanitize("@bad") == "'@bad"
    assert exports_service.sanitize("-2+3") == "'-2+3"
    assert exports_service.sanitize("\tfoo") == "'\tfoo"
    assert exports_service.sanitize("\rfoo") == "'\rfoo"
    assert exports_service.sanitize("normal") == "normal"
    assert exports_service.sanitize(None) == ""
    assert exports_service.sanitize(42) == "42"


def test_csv_no_formula_prefix_emitted() -> None:
    uid = _setup_with_malicious()
    with Session(get_engine()) as s:
        body = exports_service.export_csv(s, uid).decode("utf-8")
    # The original =, +, @, -, \t, \r characters must NOT appear at the
    # start of a description cell. We assert by checking the description
    # column is always preceded by an apostrophe for those rows.
    assert "'=cmd|'/c calc'!A1" in body
    assert "'+1+1" in body
    assert "'@SUM(1+1)" in body
    assert "'-2+3" in body
    assert "normal" in body
    # The "normal" line should not have a stray apostrophe.
    # (We rely on csv.writer producing "...,normal,..." without prefix.)
    for line in body.splitlines():
        # Find lines that contain "normal" and ensure no leading apostrophe.
        if ",normal," in line:
            assert not line.startswith("'"), f"normal got apostrophe: {line!r}"


def test_xlsx_cells_are_neutralized() -> None:
    uid = _setup_with_malicious()
    with Session(get_engine()) as s:
        body = exports_service.export_xlsx(s, uid)
    wb = load_workbook(io.BytesIO(body))
    ws = wb["Transactions"]
    descriptions = [row[4] for row in ws.iter_rows(min_row=2, values_only=True)]
    for desc in descriptions:
        # Every description must start with either ' or a normal letter.
        assert desc[0] not in ("=", "+", "@", "-", "\t", "\r"), f"unsafe: {desc!r}"
    # And the formula prefix has been replaced with an apostrophe.
    assert any(d.startswith("'=cmd") for d in descriptions)
