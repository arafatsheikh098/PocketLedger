"""Budget progress and aggregation.

A budget is a per-category monthly cap stored as integer minor units.
We compare it against the sum of expense transactions in the same
month, *in the user's timezone*. Transfers are excluded so moving
money between the user's own accounts never inflates a category.

The :func:`month_window` helper gives the [start, end) half-open
date range for a given (year, month, tz) — used by both budget
progress and the dashboard's "current month" totals so the same
definition is shared.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlmodel import Session, select

from ..models.budget import Budget
from ..models.transaction import Transaction
from ..models.user import User
from .totals import _sum_minor


def resolve_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def month_window(year: int, month: int, tz: ZoneInfo) -> tuple[_dt.date, _dt.date]:
    """Return [start, end) for a calendar month in the given timezone.

    The first instant of the month is computed in the user's tz
    and converted back to a UTC date; the resulting ``start.date()``
    is the first calendar day that *any* timezone in the world would
    see as part of that month. This keeps a transaction dated
    2026-10-01 in any tz on file showing up in the 2026-10 budget
    for any other tz, which matches what users expect from a
    "calendar month" view.
    """
    first_local = _dt.datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        next_first_local = _dt.datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        next_first_local = _dt.datetime(year, month + 1, 1, tzinfo=tz)
    start_utc = first_local.astimezone(_dt.UTC)
    end_utc = next_first_local.astimezone(_dt.UTC)
    return start_utc.date(), end_utc.date()


def current_month_window(user: User, now: _dt.datetime | None = None) -> tuple[int, int, _dt.date, _dt.date]:
    """Return (year, month, start_date, end_date) for the user's "now"."""
    tz = resolve_tz(user)
    if now is None:
        now = _dt.datetime.now(tz)
    local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    start, end = month_window(local_now.year, local_now.month, tz)
    return local_now.year, local_now.month, start, end


@dataclass
class BudgetProgress:
    budget: Budget
    spent_minor: int
    pct: int  # 0..100+ integer percentage
    status: str  # "ok" | "warning" | "over"

    @property
    def remaining_minor(self) -> int:
        return self.budget.amount_minor - self.spent_minor


def progress_for_user(
    session: Session,
    user: User,
    year: int,
    month: int,
) -> list[BudgetProgress]:
    """Compute per-budget progress for the given month."""
    tz = resolve_tz(user)
    start, end = month_window(year, month, tz)
    budgets = list(
        session.exec(
            select(Budget)
            .where(Budget.user_id == user.id)
            .where(Budget.month == f"{year:04d}-{month:02d}")
        ).all()
    )
    if not budgets:
        return []
    # Sum of negative-amount transactions per category for the window.
    by_cat_stmt = (
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .where(Transaction.date >= start)
        .where(Transaction.date < end)
        .where(Transaction.amount_minor < 0)
        .where(Transaction.is_transfer == False)  # noqa: E712
    )
    spent: dict[int, int] = {}
    for t in session.exec(by_cat_stmt).all():
        if t.category_id is None:
            continue
        # t.amount_minor is negative for expenses; flip to positive for display.
        spent[t.category_id] = spent.get(t.category_id, 0) + int(-t.amount_minor)
    out: list[BudgetProgress] = []
    for b in budgets:
        s = spent.get(b.category_id, 0)
        pct = (s * 100 // b.amount_minor) if b.amount_minor > 0 else 0
        if s >= b.amount_minor:
            status = "over"
        elif pct >= 80:
            status = "warning"
        else:
            status = "ok"
        out.append(BudgetProgress(budget=b, spent_minor=s, pct=pct, status=status))
    out.sort(key=lambda p: p.budget.category_id)
    return out


def spent_for_window(
    session: Session,
    user: User,
    year: int,
    month: int,
) -> int:
    tz = resolve_tz(user)
    start, end = month_window(year, month, tz)
    return -_sum_minor(
        session,
        user.id,
        expr=select(Transaction)
        .where(Transaction.date >= start)
        .where(Transaction.date < end)
        .where(Transaction.amount_minor < 0)
        .where(Transaction.is_transfer == False),  # noqa: E712
    )


def income_for_window(
    session: Session,
    user: User,
    year: int,
    month: int,
) -> int:
    tz = resolve_tz(user)
    start, end = month_window(year, month, tz)
    return _sum_minor(
        session,
        user.id,
        expr=select(Transaction)
        .where(Transaction.date >= start)
        .where(Transaction.date < end)
        .where(Transaction.amount_minor > 0)
        .where(Transaction.is_transfer == False),  # noqa: E712
    )


def by_category_for_window(
    session: Session,
    user: User,
    year: int,
    month: int,
) -> dict[int, int]:
    """Return {category_id: positive_spent_minor} for the window."""
    tz = resolve_tz(user)
    start, end = month_window(year, month, tz)
    stmt = (
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .where(Transaction.date >= start)
        .where(Transaction.date < end)
        .where(Transaction.amount_minor < 0)
        .where(Transaction.is_transfer == False)  # noqa: E712
    )
    out: dict[int, int] = {}
    for t in session.exec(stmt).all():
        if t.category_id is None:
            continue
        out[t.category_id] = out.get(t.category_id, 0) + int(-t.amount_minor)
    return out


def six_month_totals(
    session: Session,
    user: User,
    now: _dt.datetime | None = None,
) -> list[tuple[str, int, int]]:
    """Return [(YYYY-MM, income_minor, expense_minor), ...] for the last
    six months, oldest first. The final entry is the current month.
    """
    tz = resolve_tz(user)
    if now is None:
        now = _dt.datetime.now(tz)
    local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
    out: list[tuple[str, int, int]] = []
    for i in range(5, -1, -1):
        y = local_now.year
        m = local_now.month - i
        while m <= 0:
            m += 12
            y -= 1
        income = income_for_window(session, user, y, m)
        expense = spent_for_window(session, user, y, m)
        out.append((f"{y:04d}-{m:02d}", income, expense))
    return out
