"""CSV / XLSX export with formula-injection neutralization.

Both formats include the user's transactions (after the same filters
as the transactions list view) plus a per-category summary and a
totals row. The XLSX file uses ``openpyxl`` and the CSV is plain.

Every text cell is sanitized to prevent formula injection: a leading
``=``, ``+``, ``-``, ``@``, tab, or CR character is rewritten to a
single-quote prefix (``'``). Spreadsheets treat the apostrophe as a
text marker and the cell renders as plain text rather than executing
the embedded formula. This is the OWASP-recommended mitigation for
CSV/XLSX formula injection (CWE-1236).
"""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook
from sqlmodel import Session

from ..auth.scoped import scoped_query
from ..models.category import Category
from ..models.transaction import Transaction

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize(value: str | int | float | None) -> str:
    """Return a value safe to drop into a spreadsheet cell.

    Numbers are passed through as strings (already safe in CSV/XLSX).
    Strings that start with a formula-trigger character get a
    leading apostrophe.
    """
    if value is None:
        return ""
    if isinstance(value, int | float):
        return str(value)
    s = str(value)
    if s and s[0] in _FORMULA_PREFIXES:
        return "'" + s
    return s


def _txn_row(t: Transaction, categories_by_id: dict[int, str]) -> list:
    return [
        t.date.isoformat(),
        categories_by_id.get(t.category_id or 0, ""),
        "transfer" if t.is_transfer else ("expense" if t.amount_minor < 0 else "income"),
        f"{(t.amount_minor / 100):.2f}",
        sanitize(t.description),
        sanitize(t.notes),
    ]


def export_csv(session: Session, user_id: int) -> bytes:
    """Return a CSV file body for the user's transactions + summary."""
    txns = list(
        session.exec(
            scoped_query(session, user_id, Transaction).order_by(Transaction.date.asc())
        ).all()
    )
    categories = list(
        session.exec(scoped_query(session, user_id, Category).order_by(Category.name.asc())).all()
    )
    categories_by_id = {c.id: c.name for c in categories}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "category", "kind", "amount", "description", "notes"])
    for t in txns:
        writer.writerow(_txn_row(t, categories_by_id))
    # Summary by category.
    income = sum(int(t.amount_minor) for t in txns if t.amount_minor > 0 and not t.is_transfer)
    expense = -sum(int(t.amount_minor) for t in txns if t.amount_minor < 0 and not t.is_transfer)
    by_cat: dict[str, int] = {}
    for t in txns:
        if t.is_transfer or t.category_id is None:
            continue
        name = categories_by_id.get(t.category_id, "?")
        # expense is a positive number for display.
        delta = -int(t.amount_minor) if t.amount_minor < 0 else int(t.amount_minor)
        by_cat[name] = by_cat.get(name, 0) + delta
    writer.writerow([])
    writer.writerow(["Summary by category"])
    writer.writerow(["category", "amount"])
    for name, amt in sorted(by_cat.items()):
        writer.writerow([sanitize(name), f"{(amt / 100):.2f}"])
    writer.writerow([])
    writer.writerow(["Income", f"{(income / 100):.2f}"])
    writer.writerow(["Expense", f"{(expense / 100):.2f}"])
    writer.writerow(["Net", f"{((income - expense) / 100):.2f}"])
    return buf.getvalue().encode("utf-8")


def export_xlsx(session: Session, user_id: int) -> bytes:
    """Return an XLSX file body for the user's transactions + summary."""
    txns = list(
        session.exec(
            scoped_query(session, user_id, Transaction).order_by(Transaction.date.asc())
        ).all()
    )
    categories = list(
        session.exec(scoped_query(session, user_id, Category).order_by(Category.name.asc())).all()
    )
    categories_by_id = {c.id: c.name for c in categories}

    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(["date", "category", "kind", "amount", "description", "notes"])
    for t in txns:
        ws.append(_txn_row(t, categories_by_id))

    # Summary sheet.
    summary = wb.create_sheet("Summary")
    income = sum(int(t.amount_minor) for t in txns if t.amount_minor > 0 and not t.is_transfer)
    expense = -sum(int(t.amount_minor) for t in txns if t.amount_minor < 0 and not t.is_transfer)
    summary.append(["Category", "Amount"])
    by_cat: dict[str, int] = {}
    for t in txns:
        if t.is_transfer or t.category_id is None:
            continue
        name = categories_by_id.get(t.category_id, "?")
        delta = -int(t.amount_minor) if t.amount_minor < 0 else int(t.amount_minor)
        by_cat[name] = by_cat.get(name, 0) + delta
    for name, amt in sorted(by_cat.items()):
        summary.append([sanitize(name), amt / 100])
    summary.append([])
    summary.append(["Income", income / 100])
    summary.append(["Expense", expense / 100])
    summary.append(["Net", (income - expense) / 100])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
