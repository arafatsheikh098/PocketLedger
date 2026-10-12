"""Categorization rules: list/create/reorder/delete.

Each rule has a (case-insensitive substring) ``pattern`` and a target
``category_id``. Rules are evaluated in ascending ``position`` order,
first match wins. The list view lets the user reorder by promoting
or demoting an entry.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import select

from ..auth.scoped import scoped_get, scoped_query
from ..models.category import Category
from ..models.rule import Rule
from ..routers.deps import CurrentUser, SessionDep, require_csrf

router = APIRouter(prefix="/rules", tags=["rules"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_rules(request: Request, user: CurrentUser, session: SessionDep):
    rules = session.exec(
        scoped_query(session, user.id, Rule).order_by(Rule.position.asc(), Rule.id.asc())
    ).all()
    categories = session.exec(
        scoped_query(session, user.id, Category).order_by(Category.name.asc())
    ).all()
    return templates.TemplateResponse(
        request,
        "rules/list.html.j2",
        {
            "user": user,
            "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            "rules": rules,
            "categories": categories,
            "categories_by_id": {c.id: c.name for c in categories},
            "error": request.query_params.get("error"),
        },
    )


@router.post("", dependencies=[Depends(require_csrf)])
def create_rule(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    pattern: str = Form(...),
    category_id: int = Form(...),
):
    pattern = pattern.strip()
    if not pattern:
        return _redirect_with_error(request, "Pattern cannot be empty")
    if scoped_get(session, user.id, Category, category_id) is None:
        return _redirect_with_error(request, "Unknown category")
    # Append at the end of the user's rules.
    max_pos = session.exec(
        select(Rule.position)
        .where(Rule.user_id == user.id)
        .order_by(Rule.position.desc())
    ).first()
    next_pos = (max_pos or 0) + 1
    rule = Rule(
        user_id=user.id, pattern=pattern[:255], category_id=category_id, position=next_pos
    )
    session.add(rule)
    session.commit()
    return RedirectResponse("/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{rule_id}/delete", dependencies=[Depends(require_csrf)])
def delete_rule(
    rule_id: int, user: CurrentUser, session: SessionDep
):
    rule = scoped_get(session, user.id, Rule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    session.delete(rule)
    session.commit()
    return RedirectResponse("/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{rule_id}/up", dependencies=[Depends(require_csrf)])
def move_up(rule_id: int, user: CurrentUser, session: SessionDep):
    _swap(session, user.id, rule_id, -1)
    return RedirectResponse("/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{rule_id}/down", dependencies=[Depends(require_csrf)])
def move_down(rule_id: int, user: CurrentUser, session: SessionDep):
    _swap(session, user.id, rule_id, +1)
    return RedirectResponse("/rules", status_code=status.HTTP_303_SEE_OTHER)


def _swap(session, user_id: int, rule_id: int, direction: int) -> None:
    """Swap this rule's position with the rule at position +/- 1.

    Position gaps are tolerated: the algorithm finds the "next" rule
    in the requested direction by ordering on (position, id) and
    swapping positions so that the relative order changes but no two
    rules end up with the same position. We use position*1000+id
    arithmetic to keep them unique after a swap.
    """
    rule = scoped_get(session, user_id, Rule, rule_id)
    if rule is None:
        return
    if direction < 0:
        neighbor = session.exec(
            select(Rule)
            .where(Rule.user_id == user_id)
            .where((Rule.position < rule.position) | ((Rule.position == rule.position) & (Rule.id < rule.id)))  # type: ignore[arg-type]
            .order_by(Rule.position.desc(), Rule.id.desc())
        ).first()
    else:
        neighbor = session.exec(
            select(Rule)
            .where(Rule.user_id == user_id)
            .where((Rule.position > rule.position) | ((Rule.position == rule.position) & (Rule.id > rule.id)))  # type: ignore[arg-type]
            .order_by(Rule.position.asc(), Rule.id.asc())
        ).first()
    if neighbor is None:
        return
    rule.position, neighbor.position = neighbor.position, rule.position
    session.add(rule)
    session.add(neighbor)
    session.commit()


def _redirect_with_error(request: Request, message: str) -> RedirectResponse:
    return RedirectResponse(f"/rules?error={message}", status_code=status.HTTP_303_SEE_OTHER)
