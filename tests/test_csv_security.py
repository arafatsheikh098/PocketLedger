"""Tests for CSV import path traversal protection and staged file permissions."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth.passwords import hash_password
from app.db import get_engine
from app.models.account import Account
from app.models.user import User
from app.routers.auth import _seed_default_categories
from app.routers.imports import IMPORTS_DIR


def _setup_user(username: str = "alice") -> tuple[int, int]:
    """Create a user and default bank account, returning (user_id, account_id)."""
    with Session(get_engine()) as s:
        u = User(
            username=username,
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


def _login(client: TestClient, username: str = "alice") -> str:
    r = client.get("/auth/login")
    csrf = r.cookies.get("pocketledger_csrf", "")
    client.post(
        "/auth/login",
        data={"username": username, "password": "pw12345678", "csrf_token": csrf},
        follow_redirects=False,
    )
    return client.cookies.get("pocketledger_csrf", "")


def test_path_traversal_absolute_path_blocked(client: TestClient) -> None:
    _, account_id = _setup_user()
    csrf = _login(client)

    r = client.post(
        "/imports/dry-run",
        data={
            "account_id": str(account_id),
            "tmp_path": "/etc/passwd",
            "date_col": "0",
            "description_col": "1",
            "amount_mode": "signed",
            "amount_col": "2",
            "date_format": "%Y-%m-%d",
            "decimal_sep": ".",
            "thousands_sep": ",",
            "csrf_token": csrf,
        },
    )
    assert r.status_code == 400
    assert "invalid upload path" in r.text.lower()


def test_path_traversal_relative_dotdot_blocked(client: TestClient) -> None:
    _, account_id = _setup_user()
    csrf = _login(client)

    r = client.post(
        "/imports/dry-run",
        data={
            "account_id": str(account_id),
            "tmp_path": "../../etc/passwd",
            "date_col": "0",
            "description_col": "1",
            "amount_mode": "signed",
            "amount_col": "2",
            "date_format": "%Y-%m-%d",
            "decimal_sep": ".",
            "thousands_sep": ",",
            "csrf_token": csrf,
        },
    )
    assert r.status_code == 400
    assert "invalid upload path" in r.text.lower()


def test_cross_user_staged_file_access_blocked(client: TestClient) -> None:
    u1_id, a1_id = _setup_user("alice")
    _setup_user("bob")

    # Alice uploads a valid CSV
    csrf_alice = _login(client, "alice")
    csv_bytes = b"date,desc,amount\n2026-10-01,Coffee,-4.50\n"
    r = client.post(
        "/imports/upload",
        data={"account_id": str(a1_id), "csrf_token": csrf_alice},
        files={"file": ("test.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    # Extract the staged tmp_path token from form response
    import re
    match = re.search(r'name="tmp_path" value="([a-f0-9]+)"', r.text)
    assert match is not None
    staged_token = match.group(1)

    # Bob logs in and tries to dry-run Alice's staged token
    bob_client = TestClient(client.app)
    csrf_bob = _login(bob_client, "bob")
    r_bob = bob_client.post(
        "/imports/dry-run",
        data={
            "account_id": "2",
            "tmp_path": staged_token,
            "date_col": "0",
            "description_col": "1",
            "amount_mode": "signed",
            "amount_col": "2",
            "date_format": "%Y-%m-%d",
            "decimal_sep": ".",
            "thousands_sep": ",",
            "csrf_token": csrf_bob,
        },
    )
    # Bob is blocked with 400 or 403
    assert r_bob.status_code in (400, 403)


def test_csv_upload_dry_run_commit_flow_and_cleanup(client: TestClient) -> None:
    u_id, account_id = _setup_user()
    csrf = _login(client)

    csv_bytes = b"date,desc,amount\n2026-10-01,Salary,5000.00\n"
    r_up = client.post(
        "/imports/upload",
        data={"account_id": str(account_id), "csrf_token": csrf},
        files={"file": ("statement.csv", csv_bytes, "text/csv")},
    )
    assert r_up.status_code == 200

    import re
    match = re.search(r'name="tmp_path" value="([a-f0-9]+)"', r_up.text)
    assert match is not None
    token = match.group(1)

    staged_file = IMPORTS_DIR / f"{u_id}_{token}.csv"
    assert staged_file.is_file()
    # Check permissions on Unix (owner read/write only, e.g. 0o600)
    mode = oct(staged_file.stat().st_mode & 0o777)
    assert mode == "0o600"

    # Dry-run
    r_dry = client.post(
        "/imports/dry-run",
        data={
            "account_id": str(account_id),
            "tmp_path": token,
            "date_col": "0",
            "description_col": "1",
            "amount_mode": "signed",
            "amount_col": "2",
            "date_format": "%Y-%m-%d",
            "decimal_sep": ".",
            "thousands_sep": ",",
            "csrf_token": csrf,
        },
    )
    assert r_dry.status_code == 200
    assert "Commit 1 new rows" in r_dry.text

    # Extract mapping_json
    mapping_match = re.search(r'name="mapping_json" value=\'([^\']+)\'', r_dry.text)
    assert mapping_match is not None
    import html
    mapping_json = html.unescape(mapping_match.group(1))

    # Commit
    r_commit = client.post(
        "/imports/commit",
        data={
            "account_id": str(account_id),
            "tmp_path": token,
            "mapping_json": mapping_json,
            "filename": "statement.csv",
            "csrf_token": csrf,
        },
        follow_redirects=False,
    )
    assert r_commit.status_code == 303
    assert "/imports/" in r_commit.headers["location"]

    # Verify staged file was cleaned up
    assert not staged_file.exists()
