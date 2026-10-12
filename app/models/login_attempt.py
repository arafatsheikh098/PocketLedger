from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LoginAttempt(SQLModel, table=True):
    __tablename__ = "login_attempts"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, max_length=64)
    ip: str = Field(max_length=64)
    success: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow, index=True)
