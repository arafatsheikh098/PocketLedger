"""Command-line interface for admin tasks.

Currently just ``create-user``; kept tiny on purpose.
"""
from __future__ import annotations

import argparse
import sys

from sqlmodel import Session

from .auth.passwords import hash_password
from .config import get_settings
from .db import create_db_and_tables, get_engine
from .models.user import User
from .routers.auth import _seed_default_categories
from .sqlmodel_helpers import get_user_by_username


def cmd_create_user(username: str, password: str) -> int:
    settings = get_settings()
    create_db_and_tables()
    with Session(get_engine()) as session:
        if get_user_by_username(session, username):
            print(f"user {username!r} already exists", file=sys.stderr)
            return 1
        user = User(
            username=username,
            password_hash=hash_password(password),
            base_currency=settings.default_currency,
            timezone=settings.user_timezone,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        _seed_default_categories(session, user.id)
        print(f"created user {username} (id={user.id})")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-user", help="create a new user with default categories")
    p.add_argument("--username", required=True)
    p.add_argument("--password", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "create-user":
        return cmd_create_user(args.username, args.password)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
