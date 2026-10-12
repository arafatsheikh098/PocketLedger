"""Accounts CRUD.

Every list/get/create/update/delete is scoped to ``current_user`` via
``app.auth.scoped.scoped_get`` / ``scoped_query``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.scoped import scoped_get, scoped_query
from ..models.account import ACCOUNT_TYPES, Account
from ..models.transaction import Transaction
from ..routers.deps import CurrentUser, SessionDep, is_demo, require_csrf

router = APIRouter(prefix="/accounts", tags=["accounts"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_accounts(request: Request, user: CurrentUser, session: SessionDep):
    accounts = session.exec(scoped_query(session, user.id, Account)).all()
    txn_counts: dict[int, int] = {}
    if accounts:
        stmt = scoped_query(session, user.id, Transaction).where(
            Transaction.account_id.in_([a.id for a in accounts if a.id is not None])
        )
        for t in session.exec(stmt).all():
            txn_counts[t.account_id] = txn_counts.get(t.account_id, 0) + 1
    return templates.TemplateResponse(
        request,
        "accounts/list.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "account_types": ACCOUNT_TYPES,
            "accounts": accounts,
            "txn_counts": txn_counts,
            "error": None,
        },
    )


@router.post("", response_model=None)
def create_account(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    name: str = Form(...),
    type: str = Form(...),
):
    if type not in ACCOUNT_TYPES:
        return _error_redirect("invalid account type")
    name = name.strip()
    if not name:
        return _error_redirect("name is required")
    session.add(Account(user_id=user.id, name=name, type=type))
    session.commit()
    return RedirectResponse("/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/delete", response_model=None)
def delete_account(
    account_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
):
    account = scoped_get(session, user.id, Account, account_id)
    if account is None:
        raise HTTPException(status_code=404)
    # Per F3.6, block deletion of an account that still has transactions.
    txns = session.exec(
        scoped_query(session, user.id, Transaction).where(Transaction.account_id == account_id)
    ).all()
    if txns:
        return RedirectResponse(
            f"/accounts?error=Account+has+{len(txns)}+transactions.+Move+or+delete+them+first.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    session.delete(account)
    session.commit()
    return RedirectResponse("/accounts", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{account_id}/rename", response_model=None)
def rename_account(
    account_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    name: str = Form(...),
):
    account = scoped_get(session, user.id, Account, account_id)
    if account is None:
        raise HTTPException(status_code=404)
    account.name = name.strip()
    session.add(account)
    session.commit()
    return RedirectResponse("/accounts", status_code=status.HTTP_303_SEE_OTHER)


def _error_redirect(message: str) -> RedirectResponse:
    from urllib.parse import quote

    return RedirectResponse(f"/accounts?error={quote(message)}", status_code=303)
