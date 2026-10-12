"""Authentication routes: login, logout, change password, optional register.

All state-changing routes depend on :func:`require_csrf`. The login
form itself issues a fresh CSRF token on every GET so a logged-out
client can submit it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth.csrf import make_csrf_token
from ..auth.passwords import hash_password, verify_password
from ..auth.rate_limit import is_locked, record
from ..config import get_settings
from ..models.category import DEFAULT_CATEGORIES, Category
from ..models.user import User
from ..routers.deps import (
    CSRF_COOKIE,
    CurrentUser,
    CurrentUserOptional,
    SessionDep,
    clear_session_cookies,
    require_csrf,
    set_session_cookies,
)
from ..sqlmodel_helpers import get_user_by_username

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory="app/templates")


def _settings():
    return get_settings()


def _seed_default_categories(session, user_id: int) -> None:
    for name in DEFAULT_CATEGORIES:
        session.add(Category(user_id=user_id, name=name, is_default=True))
    session.commit()


def _render_login(request: Request, user: User | None, error: str | None = None) -> HTMLResponse:
    settings = _settings()
    # Read CSRF cookie if present; otherwise issue a new one.
    csrf_cookie = request.cookies.get(CSRF_COOKIE) or make_csrf_token()
    response = templates.TemplateResponse(
        request,
        "login.html.j2",
        {
            "user": user,
            "demo_mode": settings.demo_mode,
            "allow_registration": settings.allow_registration,
            "csrf_token": csrf_cookie,
            "error": error,
        },
    )
    # Always refresh the CSRF cookie on the login page.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_cookie,
        httponly=False,
        samesite="lax",
        secure=settings.is_production,
    )
    return response


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, user: CurrentUserOptional) -> HTMLResponse:
    return _render_login(request, user)


@router.post("/login", response_model=None)
def login_post(
    request: Request,
    session: SessionDep,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(default=""),
):
    ip = request.client.host if request.client else "unknown"

    # CSRF is enforced for all POSTs, including login.
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    from ..auth.csrf import verify_csrf

    if not verify_csrf(csrf_cookie, csrf_token):
        return _render_login(request, None, error="session expired, please try again")

    if is_locked(session, username, ip):
        return _render_login(request, None, error="too many failed attempts, try again later")

    user = get_user_by_username(session, username)
    if user is None or not verify_password(user.password_hash, password):
        record(session, username, ip, success=False)
        return _render_login(request, None, error="invalid username or password")

    record(session, username, ip, success=True)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookies(response, user.id)
    return response


@router.post("/logout")
def logout(_user: CurrentUser, _csrf: None = Depends(require_csrf)) -> RedirectResponse:
    response = RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookies(response)
    return response


@router.get("/change-password", response_class=HTMLResponse)
def change_password_form(request: Request, user: CurrentUser) -> HTMLResponse:
    csrf_cookie = request.cookies.get(CSRF_COOKIE) or make_csrf_token()
    response = templates.TemplateResponse(
        request,
        "change_password.html.j2",
        {
            "user": user,
            "demo_mode": _settings().demo_mode,
            "allow_registration": _settings().allow_registration,
            "csrf_token": csrf_cookie,
            "error": None,
        },
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_cookie,
        httponly=False,
        samesite="lax",
        secure=_settings().is_production,
    )
    return response


@router.post("/change-password", response_model=None)
def change_password_post(
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    _csrf: None = Depends(require_csrf),
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    if not verify_password(user.password_hash, current_password):
        return templates.TemplateResponse(
            request,
            "change_password.html.j2",
            {
                "user": user,
                "demo_mode": _settings().demo_mode,
                "allow_registration": _settings().allow_registration,
                "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "error": "current password is incorrect",
            },
            status_code=400,
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "change_password.html.j2",
            {
                "user": user,
                "demo_mode": _settings().demo_mode,
                "allow_registration": _settings().allow_registration,
                "csrf_token": request.cookies.get(CSRF_COOKIE, ""),
                "error": "new password must be at least 8 characters",
            },
            status_code=400,
        )
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, user: CurrentUserOptional) -> HTMLResponse:
    settings = _settings()
    if not settings.allow_registration:
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    csrf_cookie = request.cookies.get(CSRF_COOKIE) or make_csrf_token()
    response = templates.TemplateResponse(
        request,
        "register.html.j2",
        {
            "user": user,
            "demo_mode": settings.demo_mode,
            "allow_registration": settings.allow_registration,
            "csrf_token": csrf_cookie,
            "error": None,
        },
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_cookie,
        httponly=False,
        samesite="lax",
        secure=settings.is_production,
    )
    return response


@router.post("/register")
def register_post(
    request: Request,
    session: SessionDep,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(default=""),
) -> RedirectResponse:
    settings = _settings()
    if not settings.allow_registration:
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    from ..auth.csrf import verify_csrf

    if not verify_csrf(csrf_cookie, csrf_token):
        return RedirectResponse("/auth/register", status_code=status.HTTP_303_SEE_OTHER)
    if get_user_by_username(session, username):
        return RedirectResponse("/auth/register", status_code=status.HTTP_303_SEE_OTHER)
    if len(password) < 8:
        return RedirectResponse("/auth/register", status_code=status.HTTP_303_SEE_OTHER)
    new_user = User(
        username=username,
        password_hash=hash_password(password),
        base_currency=settings.default_currency,
        timezone=settings.user_timezone,
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    _seed_default_categories(session, new_user.id)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookies(response, new_user.id)
    return response


__all__ = ["router", "_seed_default_categories"]
