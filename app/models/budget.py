from __future__ import annotations

from sqlmodel import Field, SQLModel


class Budget(SQLModel, table=True):
    __tablename__ = "budgets"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    # Month as the first day of the month (UTC). e.g. 2026-10-01.
    month: str = Field(max_length=10, index=True)
    amount_minor: int
