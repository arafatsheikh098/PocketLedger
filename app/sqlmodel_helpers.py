"""Tiny SQLModel helpers used by routers.

Kept in a separate module to avoid circular imports.
"""
from __future__ import annotations

from sqlmodel import Session, select

from .models.user import User


def get_user_by_id(session: Session, user_id: int) -> User | None:
    return session.exec(select(User).where(User.id == user_id)).first()


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.exec(select(User).where(User.username == username)).first()
