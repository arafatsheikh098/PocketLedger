"""Per-request dependencies.

The :func:`current_user_optional` and :func:`current_user` dependencies
are the only places that read the session cookie. Routes that mutate
state additionally depend on ``require_csrf`` (or call its body inline).
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Cookie, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from ..auth.csrf import make_csrf_token, verify_csrf
from ..auth.sessions import make_session_cookie, read_session_cookie
from ..config import get_settings
from ..db import get_session
from ..models.user import User
from ..sqlmodel_helpers import get_user_by_id

SESSION_COOKIE = "pocketledger_session"
CSRF_COOKIE = "pocketledger_csrf"


def db_session() -> Generator[Session, None, None]:
    yield from get_session()


SessionDep = Annotated[Session, Depends(db_session)]


def current_user_optional(
    session: SessionDep,
    pocketledger_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> User | None:
    if not pocketledger_session:
        return None
    uid = read_session_cookie(pocketledger_session)
    if uid is None:
        return None
    return get_user_by_id(session, uid)


CurrentUserOptional = Annotated[User | None, Depends(current_user_optional)]


def current_user(user: CurrentUserOptional) -> User:
    if user is None:
        # Routes that depend on current_user get a 303 redirect to login.
        # We do that via raising HTTPException with a Location header.
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_csrf(
    request: Request,
    user: CurrentUser,
    csrf_from_form: Annotated[str | None, Form(alias="csrf_token")] = None,
    csrf_from_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    pocketledger_csrf: Annotated[str | None, Cookie(alias=CSRF_COOKIE)] = None,
) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    provided = csrf_from_form or csrf_from_header
    if not verify_csrf(pocketledger_csrf, provided):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid csrf token")


def settings_dep():
    return get_settings()


def make_csrf_for_user() -> str:
    return make_csrf_token()


def set_session_cookies(response: RedirectResponse, user_id: int) -> str:
    """Attach session + CSRF cookies to a redirect response.

    Returns the new CSRF token so the caller can also embed it in
    templates if needed.
    """
    session_value = make_session_cookie(user_id)
    csrf_value = make_csrf_token()
    response.set_cookie(
        SESSION_COOKIE,
        session_value,
        httponly=True,
        samesite="lax",
        secure=get_settings().is_production,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_value,
        httponly=False,  # readable by JS so it can be put in fetch headers
        samesite="lax",
        secure=get_settings().is_production,
    )
    return csrf_value


def clear_session_cookies(response: RedirectResponse) -> None:
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)
