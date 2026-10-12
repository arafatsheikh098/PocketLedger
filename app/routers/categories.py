"""Categories CRUD.

The default categories per F2.4 are seeded at user creation; this
router adds the user's custom categories on top.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.scoped import scoped_get, scoped_query
from ..models.category import Category
from ..models.transaction import Transaction
from ..routers.deps import CurrentUser, SessionDep, is_demo, require_csrf

router = APIRouter(prefix="/categories", tags=["categories"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_categories(request: Request, user: CurrentUser, session: SessionDep):
    categories = session.exec(
        scoped_query(session, user.id, Category).order_by(Category.is_default.desc(), Category.name)
    ).all()
    usage: dict[int, int] = {}
    for c in categories:
        if c.id is None:
            continue
        usage[c.id] = len(
            session.exec(
                scoped_query(session, user.id, Transaction).where(Transaction.category_id == c.id)
            ).all()
        )
    return templates.TemplateResponse(
        request,
        "categories/list.html.j2",
        {
            "user": user,
            "demo_mode": is_demo(request),
            "allow_registration": False,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "categories": categories,
            "usage": usage,
            "error": request.query_params.get("error"),
        },
    )


@router.post("", response_model=None)
def create_category(
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    name: str = Form(...),
):
    name = name.strip()
    if not name:
        return RedirectResponse("/categories?error=name+is+required", status_code=303)
    session.add(Category(user_id=user.id, name=name, is_default=False))
    session.commit()
    return RedirectResponse("/categories", status_code=303)


@router.post("/{category_id}/delete", response_model=None)
def delete_category(
    category_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
):
    cat = scoped_get(session, user.id, Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404)
    if cat.is_default:
        return RedirectResponse(
            "/categories?error=Cannot+delete+a+default+category", status_code=303
        )
    # Reassign transactions to None (uncategorized) so the FK is not violated.
    txns = session.exec(
        scoped_query(session, user.id, Transaction).where(Transaction.category_id == category_id)
    ).all()
    for t in txns:
        t.category_id = None
        t.manual_category = False
        session.add(t)
    session.delete(cat)
    session.commit()
    return RedirectResponse("/categories", status_code=303)


@router.post("/{category_id}/rename", response_model=None)
def rename_category(
    category_id: int,
    user: CurrentUser,
    session: SessionDep,
    _csrf: None = Depends(require_csrf),
    name: str = Form(...),
):
    cat = scoped_get(session, user.id, Category, category_id)
    if cat is None:
        raise HTTPException(status_code=404)
    cat.name = name.strip()
    session.add(cat)
    session.commit()
    return RedirectResponse("/categories", status_code=303)
