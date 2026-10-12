"""Budgets: set / list / delete per-category monthly caps."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from ..auth.scoped import scoped_get, scoped_query
from ..models.budget import Budget
from ..models.category import Category
from ..money import MoneyParseError, parse
from ..routers.deps import CurrentUser, SessionDep, require_csrf
from ..services import budgets as budgets_service

router = APIRouter(prefix="/budgets", tags=["budgets"])
templates = Jinja2Templates(directory="app/templates")


def _month_from_query(month: str | None) -> tuple[int, int]:
    """Parse a YYYY-MM string into (year, month) or default to current."""
    if month:
        try:
            y_str, m_str = month.split("-", 1)
            return int(y_str), int(m_str)
        except (ValueError, AttributeError):
            pass
    now = datetime.now(ZoneInfo("UTC"))
    return now.year, now.month


@router.get("")
def list_budgets(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    month: str | None = None,
):
    year, m = _month_from_query(month)
    categories = session.exec(
        scoped_query(session, user.id, Category).order_by(Category.name.asc())
    ).all()
    categories_by_id = {c.id: c.name for c in categories}
    progress = budgets_service.progress_for_user(session, user, year, m)
    budgets_by_cat: dict[int, budgets_service.BudgetProgress] = {
        p.budget.category_id: p for p in progress
    }
    return templates.TemplateResponse(
        request,
        "budgets/list.html.j2",
        {
            "user": user,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "categories": categories,
            "categories_by_id": categories_by_id,
            "year": year,
            "month": m,
            "month_str": f"{year:04d}-{m:02d}",
            "rows": progress,
            "budgets_by_cat": budgets_by_cat,
            "error": request.query_params.get("error"),
        },
    )


@router.post("", dependencies=[Depends(require_csrf)])
def upsert_budget(
    user: CurrentUser,
    session: SessionDep,
    category_id: int = Form(...),
    month: str = Form(...),
    amount: str = Form(...),
):
    if scoped_get(session, user.id, Category, category_id) is None:
        return RedirectResponse(
            f"/budgets?month={month}&error=invalid+category", status_code=303
        )
    try:
        amt_minor = parse(amount)
    except MoneyParseError as e:
        return RedirectResponse(
            f"/budgets?month={month}&error=amount:+{e}", status_code=303
        )
    if amt_minor <= 0:
        return RedirectResponse(
            f"/budgets?month={month}&error=amount+must+be+positive", status_code=303
        )
    # Upsert: same (user, category, month) row gets its amount replaced.
    existing = session.exec(
        select(Budget)
        .where(Budget.user_id == user.id)
        .where(Budget.category_id == category_id)
        .where(Budget.month == month)
    ).first()
    if existing is None:
        b = Budget(
            user_id=user.id,
            category_id=category_id,
            month=month,
            amount_minor=amt_minor,
        )
        session.add(b)
    else:
        existing.amount_minor = amt_minor
        session.add(existing)
    session.commit()
    return RedirectResponse(f"/budgets?month={month}", status_code=303)


@router.post("/{budget_id}/delete", dependencies=[Depends(require_csrf)])
def delete_budget(budget_id: int, user: CurrentUser, session: SessionDep):
    b = scoped_get(session, user.id, Budget, budget_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    month = b.month
    session.delete(b)
    session.commit()
    return RedirectResponse(f"/budgets?month={month}", status_code=303)
