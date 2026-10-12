from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ImportBatch(SQLModel, table=True):
    __tablename__ = "import_batches"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    filename: str = Field(max_length=255)
    # JSON-serialized mapping profile used to import this batch.
    mapping_json: str = Field(default="{}", max_length=4000)
    row_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow)
    undone: bool = Field(default=False)
