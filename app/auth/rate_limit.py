"""Database-backed login rate limit.

We allow at most 5 failed attempts per (username, ip) in 15 minutes.
Successful logins reset the counter for that pair. The check is
applied inside the login route, not at the middleware level, so
attempts on a nonexistent username still count (they cost the same
DB write).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from ..models.login_attempt import LoginAttempt

WINDOW = timedelta(minutes=15)
MAX_FAILS = 5


def recent_failures(session: Session, username: str, ip: str) -> int:
    since = datetime.now(UTC) - WINDOW
    stmt = (
        select(LoginAttempt)
        .where(LoginAttempt.username == username)
        .where(LoginAttempt.ip == ip)
        .where(LoginAttempt.created_at >= since)
        .where(LoginAttempt.success == False)  # noqa: E712
    )
    return len(session.exec(stmt).all())


def is_locked(session: Session, username: str, ip: str) -> bool:
    return recent_failures(session, username, ip) >= MAX_FAILS


def record(session: Session, username: str, ip: str, success: bool) -> None:
    session.add(LoginAttempt(username=username, ip=ip, success=success))
    session.commit()
