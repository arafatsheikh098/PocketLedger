"""Totals for transactions: income, expense, net.

Transfers are always excluded so the dashboard and budget math
never double-counts money moving between the user's own accounts.
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..models.transaction import Transaction


def _sum_minor(session: Session, user_id: int, *, expr) -> int:
    """Sum amount_minor across a filtered query, returning integer minor units."""
    stmt = expr.where(Transaction.user_id == user_id)
    rows = session.exec(stmt).all()
    return sum(int(t.amount_minor) for t in rows)


def income_minor(session: Session, user_id: int) -> int:
    return _sum_minor(
        session,
        user_id,
        expr=select(Transaction).where(
            Transaction.amount_minor > 0,
            Transaction.is_transfer == False,  # noqa: E712
        ),
    )


def expense_minor(session: Session, user_id: int) -> int:
    # Expense is reported as a positive number of minor units (e.g. $12.34 = 1234).
    return -_sum_minor(
        session,
        user_id,
        expr=select(Transaction).where(
            Transaction.amount_minor < 0,
            Transaction.is_transfer == False,  # noqa: E712
        ),
    )


def net_minor(session: Session, user_id: int) -> int:
    return _sum_minor(
        session,
        user_id,
        expr=select(Transaction).where(Transaction.is_transfer == False),  # noqa: E712
    )


def by_category_minor(
    session: Session, user_id: int, *, only_uncategorized: bool = False
) -> dict[int, int]:
    """Return {category_id: sum_minor} for non-transfer transactions.

    Negative category_ids (uncategorized rows) become 0.
    """
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.is_transfer == False,  # noqa: E712
    )
    if only_uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    out: dict[int, int] = {}
    for t in session.exec(stmt).all():
        key = int(t.category_id) if t.category_id is not None else 0
        out[key] = out.get(key, 0) + int(t.amount_minor)
    return out
