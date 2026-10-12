from __future__ import annotations

from datetime import UTC, date, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    category_id: int | None = Field(default=None, foreign_key="categories.id", index=True)
    # Stored as a real calendar date (no time component). Timezones in F6
    # only affect which calendar month a date falls in.
    date: date
    # Money in integer minor units. Expenses are negative, income positive.
    amount_minor: int
    currency: str = Field(default="USD", max_length=8)
    description: str = Field(max_length=255)
    notes: str = Field(default="", max_length=1000)
    is_transfer: bool = Field(default=False)
    # If True, the category was chosen by hand and rules must not overwrite.
    manual_category: bool = Field(default=False)
    # The import batch this row came from (None for manually entered).
    import_batch_id: int | None = Field(default=None, foreign_key="import_batches.id", index=True)
    # Dedup key is sha256(account_id|iso_date|amount_minor|normalized_desc|occurrence_index).
    # Indexed to make the dedup probe fast on import.
    dedup_key: str = Field(max_length=64, index=True, default="")
    created_at: datetime = Field(default_factory=_utcnow)
