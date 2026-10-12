"""CSV import batch service.

Dry-run, atomic commit, and undo. The wizard calls :func:`dry_run`
to show the user the projected new/duplicates/errors, then
:func:`commit` to write everything in a single transaction. :func:`undo`
deletes exactly the rows a batch added.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from sqlmodel import Session, select

from ..models.account import Account
from ..models.import_batch import ImportBatch
from ..models.transaction import Transaction
from . import csv_detect, mapping
from .dedup import make_dedup_key


class RowError(Exception):
    def __init__(self, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(f"line {line_number}: {reason}")


@dataclass
class RowPreview:
    line_number: int
    date: date | None
    amount_minor: int | None
    description: str
    is_transfer: bool
    status: str  # "new" | "duplicate" | "error"
    reason: str | None = None


@dataclass
class DryRunResult:
    rows: list[RowPreview] = field(default_factory=list)
    new_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    detection: csv_detect.Detection | None = None

    def add(self, row: RowPreview) -> None:
        self.rows.append(row)
        if row.status == "new":
            self.new_count += 1
        elif row.status == "duplicate":
            self.duplicate_count += 1
        elif row.status == "error":
            self.error_count += 1


def _build_raw_value(
    row: list[str],
    m: mapping.Mapping,
) -> str:
    """Return the per-row amount raw value (string)."""
    if m.amount_mode == "signed":
        if m.amount_col is None or m.amount_col >= len(row):
            raise mapping.RowError("amount column missing")
        return row[m.amount_col]
    # debit/credit
    if m.debit_col is None or m.credit_col is None:
        raise mapping.RowError("debit/credit columns missing")
    if m.debit_col >= len(row) or m.credit_col >= len(row):
        raise mapping.RowError("debit/credit column out of range")
    return f"{row[m.debit_col]}|{row[m.credit_col]}"


def _build_dedup_keys(
    session: Session,
    user_id: int,
    account_id: int,
    rows: list[tuple[int, date, int, str, bool]],
) -> list[tuple[int, date, int, str, bool, int, str]]:
    """Return tuples extended with (occurrence_index, dedup_key).

    The dedup key is stable: re-importing the same file produces the
    same keys, so the commit step sees them as duplicates and inserts
    nothing. The occurrence_index is purely an in-batch counter that
    resets per (date, amount, normalized_description) tuple; existing
    rows in the DB are at fixed indices (0, 1, ...) and are matched
    against by their key, never by re-indexing the new batch around
    them.

    This guarantees:

    * Fresh import of two identical same-day rows -> keys for N=0, N=1
      (the spec's "occurrence index" rule).
    * Re-import of the same file -> every computed key already exists,
      so the batch inserts 0 rows.
    * Edit one row out, then re-import -> only the missing row fills
      its old slot, no duplicates.

    The existing-keys check itself is done in :func:`commit` /
    :func:`dry_run` after this function returns.
    """
    out: list[tuple[int, date, int, str, bool, int, str]] = []
    seen_in_batch: dict[tuple[date, int, str], int] = {}
    for line_no, d, amt, desc, is_transfer in rows:
        norm = mapping.normalize_for_dedup(desc)
        key = (d, amt, norm)
        n = seen_in_batch.get(key, 0)
        dk = make_dedup_key(
            account_id=account_id,
            iso_date=d.isoformat(),
            amount_minor=amt,
            description=desc,
            occurrence_index=n,
        )
        out.append((line_no, d, amt, desc, is_transfer, n, dk))
        seen_in_batch[key] = n + 1
    return out


def _parse_row(
    row: list[str],
    m: mapping.Mapping,
) -> tuple[date, int, str, bool]:
    """Parse a single row into (date, amount_minor, description, is_transfer).

    Raises :class:`mapping.RowError` on bad data.
    """
    if m.date_col >= len(row) or m.description_col >= len(row):
        raise mapping.RowError("date or description column out of range")
    d = mapping.parse_date(row[m.date_col], m.date_format)
    raw_amount = _build_raw_value(row, m)
    amount_minor = mapping.parse_amount(raw_amount, mode="", mapping=m)
    description = row[m.description_col].strip()
    is_transfer = False
    if m.is_transfer_col is not None and m.is_transfer_col < len(row):
        cell = row[m.is_transfer_col].strip().lower()
        is_transfer = cell in ("1", "true", "yes", "y", "t")
    return d, amount_minor, description, is_transfer


def dry_run(
    *,
    session: Session,
    user_id: int,
    account_id: int,
    raw_bytes: bytes,
    m: mapping.Mapping,
) -> DryRunResult:
    det = csv_detect.detect(raw_bytes)
    rows = csv_detect.all_rows(det.text, det.delimiter)
    result = DryRunResult(detection=det)
    if not rows:
        return result
    if m.has_header:
        rows = rows[1:]
    parsed: list[tuple[int, date, int, str, bool]] = []
    errors: list[tuple[int, str]] = []
    for i, row in enumerate(rows):
        line_no = i + 1
        # Skip blank rows.
        if not any(cell.strip() for cell in row):
            continue
        try:
            d, amt, desc, is_transfer = _parse_row(row, m)
        except mapping.RowError as exc:
            errors.append((line_no, str(exc)))
            continue
        parsed.append((line_no, d, amt, desc, is_transfer))

    # Compute dedup keys and decide new vs duplicate.
    extended = _build_dedup_keys(session, user_id, account_id, parsed)
    existing_keys = set(
        session.exec(
            select(Transaction.dedup_key).where(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
            )
        ).all()
    )
    by_line: dict[int, tuple[date, int, str, bool, int, str]] = {
        ln: (d, amt, desc, is_transfer, idx, dk) for (ln, d, amt, desc, is_transfer, idx, dk) in extended
    }
    parsed_by_line = {ln: (d, amt, desc, is_transfer) for (ln, d, amt, desc, is_transfer) in parsed}

    for line_no, d, amt, desc, is_transfer in parsed:
        _, _, _, _, _, dk = by_line[line_no]
        status = "duplicate" if dk in existing_keys else "new"
        result.add(
            RowPreview(
                line_number=line_no,
                date=d,
                amount_minor=amt,
                description=desc,
                is_transfer=is_transfer,
                status=status,
            )
        )

    for line_no, reason in errors:
        result.add(
            RowPreview(
                line_number=line_no,
                date=None,
                amount_minor=None,
                description="",
                is_transfer=False,
                status="error",
                reason=reason,
            )
        )

    result.rows.sort(key=lambda r: r.line_number)
    return result


def commit(
    *,
    session: Session,
    user_id: int,
    account_id: int,
    filename: str,
    raw_bytes: bytes,
    m: mapping.Mapping,
    skip_errors: bool = True,
) -> tuple[ImportBatch, list[RowError]]:
    """Parse and write the import as a single transaction.

    Returns (import_batch, errors). If ``skip_errors`` is True, error
    rows are reported but not raised; the import is still atomic for
    the good rows. If False, any row error aborts the whole import.
    """
    det = csv_detect.detect(raw_bytes)
    rows = csv_detect.all_rows(det.text, det.delimiter)
    if m.has_header and rows:
        rows = rows[1:]
    if not rows:
        return _empty_batch(session, user_id, account_id, filename, m), []

    errors: list[RowError] = []
    parsed: list[tuple[int, date, int, str, bool]] = []
    for i, row in enumerate(rows):
        line_no = i + 1
        if not any(cell.strip() for cell in row):
            continue
        try:
            d, amt, desc, is_transfer = _parse_row(row, m)
        except mapping.RowError as exc:
            errors.append(RowError(line_no, str(exc)))
            continue
        parsed.append((line_no, d, amt, desc, is_transfer))

    if errors and not skip_errors:
        # Atomic: report and roll back.
        raise mapping.RowError("; ".join(f"line {e.line_number}: {e.reason}" for e in errors))

    extended = _build_dedup_keys(session, user_id, account_id, parsed)
    existing_keys = set(
        session.exec(
            select(Transaction.dedup_key).where(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
            )
        ).all()
    )

    batch = ImportBatch(
        user_id=user_id,
        account_id=account_id,
        filename=filename,
        mapping_json=m.to_json(),
        row_count=0,
    )
    session.add(batch)
    session.flush()  # assign batch.id
    written = 0
    from ..models.user import User

    u = session.get(User, user_id)
    base_currency = u.base_currency if u is not None else "USD"
    for line_no, d, amt, desc, is_transfer, idx, dk in extended:
        if dk in existing_keys:
            continue
        t = Transaction(
            user_id=user_id,
            account_id=account_id,
            date=d,
            amount_minor=amt,
            currency=base_currency,
            description=desc,
            is_transfer=is_transfer,
            import_batch_id=batch.id,
            dedup_key=dk,
        )
        session.add(t)
        written += 1
    batch.row_count = written
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch, errors


def undo(session: Session, user_id: int, batch_id: int) -> int:
    """Delete every row a batch added. Returns the count of rows removed."""
    batch = session.get(ImportBatch, batch_id)
    if batch is None or batch.user_id != user_id or batch.undone:
        return 0
    rows = session.exec(
        select(Transaction).where(Transaction.import_batch_id == batch_id)
    ).all()
    count = len(rows)
    for t in rows:
        session.delete(t)
    batch.undone = True
    session.add(batch)
    session.commit()
    return count


def _empty_batch(
    session: Session, user_id: int, account_id: int, filename: str, m: mapping.Mapping
) -> ImportBatch:
    batch = ImportBatch(
        user_id=user_id,
        account_id=account_id,
        filename=filename,
        mapping_json=m.to_json(),
        row_count=0,
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch
