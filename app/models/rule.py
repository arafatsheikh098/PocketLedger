from __future__ import annotations

from sqlmodel import Field, SQLModel


class Rule(SQLModel, table=True):
    __tablename__ = "rules"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    # Case-insensitive substring matched against the trimmed description.
    pattern: str = Field(max_length=255)
    category_id: int = Field(foreign_key="categories.id", index=True)
    # Lower position = higher priority. First match wins.
    position: int = Field(default=0, index=True)
