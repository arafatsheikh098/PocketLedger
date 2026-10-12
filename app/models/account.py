from __future__ import annotations

from sqlmodel import Field, SQLModel

# Allowed account types per F2.
ACCOUNT_TYPES = ("bank", "mobile_wallet", "cash", "card")


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=64)
    type: str = Field(max_length=16)
