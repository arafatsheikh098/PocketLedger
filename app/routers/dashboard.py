"""Dashboard: current month totals, top categories, 6-month trend.

Renders a single page that shows the numbers in tables (always
present and accessible) and identical data as Chart.js charts when
JavaScript is enabled. The table values must match the chart values
exactly; the Playwright + table-fallback tests pin that equality.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from ..auth.scoped import scoped_query
from ..models.category import Category
from ..routers.deps import CurrentUser, SessionDep
from ..services import budgets as budgets_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def dashboard(request: Request, user: CurrentUser, session: SessionDep):
    year, month, _start, _end = budgets_service.current_month_window(user)
    income = budgets_service.income_for_window(session, user, year, month)
    expense = budgets_service.spent_for_window(session, user, year, month)
    by_cat = budgets_service.by_category_for_window(session, user, year, month)
    # Top categories: by amount descending, capped to 10.
    categories = list(
        session.exec(scoped_query(session, user.id, Category).order_by(Category.name.asc())).all()
    )
    name_by_id = {c.id: c.name for c in categories}
    top = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:10]
    top_rows = [
        {"name": name_by_id.get(cid, "?"), "amount_minor": amt} for cid, amt in top
    ]
    six = budgets_service.six_month_totals(session, user)
    progress = budgets_service.progress_for_user(session, user, year, month)
    return templates.TemplateResponse(
        request,
        "dashboard.html.j2",
        {
            "user": user,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "year": year,
            "month": month,
            "month_str": f"{year:04d}-{month:02d}",
            "income_minor": income,
            "expense_minor": expense,
            "net_minor": income - expense,
            "top_rows": top_rows,
            "six_months": [
                {"label": lbl, "income_minor": inc, "expense_minor": exp}
                for lbl, inc, exp in six
            ],
            "progress": [
                {
                    "category_id": p.budget.category_id,
                    "category_name": name_by_id.get(p.budget.category_id, "?"),
                    "amount_minor": p.budget.amount_minor,
                    "spent_minor": p.spent_minor,
                    "pct": p.pct,
                    "status": p.status,
                }
                for p in progress
            ],
        },
    )
