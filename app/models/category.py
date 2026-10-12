from __future__ import annotations

from sqlmodel import Field, SQLModel

# Default categories seeded for every new user per F2.4.
DEFAULT_CATEGORIES = (
    "Groceries",
    "Restaurants",
    "Transport",
    "Utilities",
    "Rent",
    "Salary",
    "Entertainment",
    "Health",
    "Shopping",
    "Other",
)


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=64)
    is_default: bool = Field(default=False)
