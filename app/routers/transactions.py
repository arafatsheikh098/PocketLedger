"""Transactions CRUD with filters, sort, and pagination.

Sign convention (F3.2): expenses are stored as negative integers,
income as positive integers. The UI accepts a positive number with
an "expense" / "income" choice and signs it before storage.

Transfers are excluded from totals (F3.4). The list view shows them
but they do not contribute to income/expense/budget aggregates.
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.scoped import scoped_get, scoped_query
from ..models.account import Account
from ..models.category import Category
from ..models.transaction import Transaction
from ..money import MoneyParseError, parse
from ..routers.deps import CurrentUser, SessionDep, require_csrf
from ..services.totals import expense_minor, income_minor, net_minor

router = APIRouter(prefix="/transactions", tags=["transactions"])
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 25


@router.get("")
def list_transactions(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    date_from: date_cls | None = None,
    date_to: date_cls | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    text: str | None = None,
    only_uncategorized: bool = False,
    sort: str = "date_desc",
    page: int = 1,
):
    accounts = session.exec(scoped_query(session, user.id, Account)).all()
    categories = session.exec(scoped_query(session, user.id, Category)).all()
    stmt = scoped_query(session, user.id, Transaction)
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    if account_id is not None:
        # Make sure the account actually belongs to the user.
        if scoped_get(session, user.id, Account, account_id) is None:
            account_id = None
        else:
            stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        if scoped_get(session, user.id, Category, category_id) is None:
            category_id = None
        else:
            stmt = stmt.where(Transaction.category_id == category_id)
    if only_uncategorized:
        stmt = stmt.where(Transaction.category_id.is_(None))
    if text:
        like = f"%{text}%"
        stmt = stmt.where(Transaction.description.like(like))

    sort_col, sort_dir = _resolve_sort(sort)
    stmt = stmt.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    rows = session.exec(stmt).all()
    total = len(rows)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, pages))
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start : start + PAGE_SIZE]

    return templates.TemplateResponse(
        request,
        "transactions/list.html.j2",
        {
            "user": user,
            "demo_mode": False,
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "accounts": accounts,
            "categories": categories,
            "rows": page_rows,
            "total": total,
            "page": page,
            "pages": pages,
            "filters": {
                "date_from": date_from,
                "date_to": date_to,
                "account_id": account_id,
                "category_id": category_id,
                "text": text or "",
                "only_uncategorized": only_uncategorized,
                "sort": sort,
            },
            "totals": {
                "income": income_minor(session, user.id),
                "expense": expense_minor(session, user.id),
                "net": net_minor(session, user.id),
            },
        },
    )


def _resolve_sort(sort: str):
    if sort == "date_asc":
        return Transaction.date, "asc"
    if sort == "amount_desc":
        return Transaction.amount_minor, "desc"
    if sort == "amount_asc":
        return Transaction.amount_minor, "asc"
    if sort == "description_asc":
        return Transaction.description, "asc"
    return Transaction.date, "desc"


@router.get("/new", response_model=None)
def new_form(request: Request, user: CurrentUser, session: SessionDep):
    accounts = session.exec(scoped_query(session, user.id, Account)).all()
    categories = session.exec(scoped_query(session, user.id, Category)).all()
    if not accounts:
        return RedirectResponse("/accounts?error=Create+an+account+first", status_code=303)
    return templates.TemplateResponse(
        request,
        "transactions/form.html.j2",
        {
            "user": user,
            "demo_mode": False,
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "accounts": accounts,
            "categories": categories,
            "txn": None,
            "error": None,
        },
    )


def _coerce_amount(raw: str, kind: str, is_transfer: bool) -> int:
    """Parse a positive number from the form and sign it.

    Expenses are stored negative, income positive. Transfers keep the
    sign chosen by the user (we still store it as-is, and the totals
    service excludes transfers).
    """
    if not raw.strip():
        raise MoneyParseError("amount is required")
    abs_minor = parse(raw, decimal_sep=".", thousands_sep=",")
    if is_transfer:
        return abs_minor  # sign comes from the user for transfers
    if kind == "expense":
        return -abs(abs_minor)
    if kind == "income":
        return abs(abs_minor)
    raise MoneyParseError("kind must be expense, income, or transfer")


@router.post("", response_model=None)
def create_transaction(
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    date: str = Form(...),
    amount: str = Form(...),
    kind: str = Form("expense"),
    description: str = Form(...),
    notes: str = Form(""),
    account_id: int = Form(...),
    category_id: Annotated[int | None, Form()] = None,
    is_transfer: Annotated[str | None, Form()] = None,
):
    return _save_transaction(
        user=user,
        session=session,
        date=date,
        amount=amount,
        kind=kind,
        description=description,
        notes=notes,
        account_id=account_id,
        category_id=category_id,
        is_transfer=is_transfer == "on" or is_transfer == "true",
        existing=None,
    )


@router.get("/{txn_id}/edit", response_model=None)
def edit_form(
    txn_id: int,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
):
    txn = scoped_get(session, user.id, Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404)
    accounts = session.exec(scoped_query(session, user.id, Account)).all()
    categories = session.exec(scoped_query(session, user.id, Category)).all()
    return templates.TemplateResponse(
        request,
        "transactions/form.html.j2",
        {
            "user": user,
            "demo_mode": False,
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "accounts": accounts,
            "categories": categories,
            "txn": txn,
            "error": None,
        },
    )


@router.post("/{txn_id}/edit", response_model=None)
def edit_transaction(
    txn_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    date: str = Form(...),
    amount: str = Form(...),
    kind: str = Form("expense"),
    description: str = Form(...),
    notes: str = Form(""),
    account_id: int = Form(...),
    category_id: Annotated[int | None, Form()] = None,
    is_transfer: Annotated[str | None, Form()] = None,
):
    txn = scoped_get(session, user.id, Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404)
    return _save_transaction(
        user=user,
        session=session,
        date=date,
        amount=amount,
        kind=kind,
        description=description,
        notes=notes,
        account_id=account_id,
        category_id=category_id,
        is_transfer=is_transfer == "on" or is_transfer == "true",
        existing=txn,
    )


@router.post("/{txn_id}/delete", response_model=None)
def delete_transaction(
    txn_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
):
    txn = scoped_get(session, user.id, Transaction, txn_id)
    if txn is None:
        raise HTTPException(status_code=404)
    session.delete(txn)
    session.commit()
    return RedirectResponse("/transactions", status_code=303)


def _save_transaction(
    *,
    user,
    session,
    date: str,
    amount: str,
    kind: str,
    description: str,
    notes: str,
    account_id: int,
    category_id: int | None,
    is_transfer: bool,
    existing: Transaction | None,
):
    try:
        d = date_cls.fromisoformat(date)
    except ValueError:
        return _redirect_with_error("invalid date (YYYY-MM-DD)")
    try:
        signed = _coerce_amount(amount, kind, is_transfer)
    except MoneyParseError as e:
        return _redirect_with_error(f"amount: {e}")

    account = scoped_get(session, user.id, Account, account_id)
    if account is None:
        return _redirect_with_error("invalid account")
    if category_id is not None and scoped_get(session, user.id, Category, category_id) is None:
        return _redirect_with_error("invalid category")

    if existing is None:
        existing = Transaction(
            user_id=user.id,
            account_id=account_id,
            date=d,
            amount_minor=signed,
            currency=user.base_currency,
            description=description.strip(),
            notes=notes,
            is_transfer=is_transfer,
            manual_category=category_id is not None,
        )
        existing.category_id = category_id
        # Manual dedup_key for manual entries: no import batch, so we use a unique token.
        import secrets as _secrets

        existing.dedup_key = _secrets.token_hex(16)
        session.add(existing)
    else:
        existing.date = d
        existing.amount_minor = signed
        existing.description = description.strip()
        existing.notes = notes
        existing.account_id = account_id
        existing.is_transfer = is_transfer
        if category_id is not None:
            existing.manual_category = True
        existing.category_id = category_id
        session.add(existing)
    session.commit()
    return RedirectResponse("/transactions", status_code=303)


def _redirect_with_error(msg: str) -> RedirectResponse:
    from urllib.parse import quote

    return RedirectResponse(f"/transactions?error={quote(msg)}", status_code=303)
