from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=64)
    password_hash: str = Field(max_length=255)
    base_currency: str = Field(default="USD", max_length=8)
    timezone: str = Field(default="UTC", max_length=64)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
