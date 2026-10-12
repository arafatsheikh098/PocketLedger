"""FastAPI app factory.

This is the only place that wires routers, middleware, and the static
file mount together. Tests call ``create_app()`` to get a fresh app;
production calls ``uvicorn app.main:app``.

Routers are added incrementally as each milestone is implemented:
  M2: auth + a small landing page so logout and home redirect work.
  M3..M7 add the resource routers.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings, get_settings
from .routers.deps import CurrentUserOptional


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    if settings.is_production and settings.secret_key.startswith("change-me"):
        raise RuntimeError(
            "SECRET_KEY is the default value. Set a real SECRET_KEY in production."
        )

    app = FastAPI(title="PocketLedger", version="0.1.0")

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    templates = Jinja2Templates(directory="app/templates")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_model=None)
    def home(request: Request, user: CurrentUserOptional):
        if user is None:
            return RedirectResponse("/auth/login", status_code=303)
        return templates.TemplateResponse(
            request,
            "home.html.j2",
            {
                "user": user,
                "demo_mode": settings.demo_mode,
                "allow_registration": settings.allow_registration,
                "csrf_token": request.cookies.get("pocketledger_csrf", ""),
            },
        )

    from .routers.auth import router as auth_router

    app.include_router(auth_router)
    _include_feature_routers(app)
    _register_demo_middleware(app, settings)

    return app


def _include_feature_routers(app: FastAPI) -> None:
    """Attach feature routers if they exist (added in later milestones)."""
    from importlib import import_module

    for name in (
        "app.routers.accounts",
        "app.routers.categories",
        "app.routers.transactions",
        "app.routers.rules",
        "app.routers.budgets",
        "app.routers.imports",
        "app.routers.exports",
        "app.routers.dashboard",
    ):
        try:
            mod = import_module(name)
        except ModuleNotFoundError:
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router)


def _register_demo_middleware(app: FastAPI, settings: Settings) -> None:
    """If DEMO_MODE is on, every page renders the banner (via base.html).

    The banner is controlled by the ``demo_mode`` template variable;
    this function exists so M7 can attach a single hook here without
    touching every router.
    """
    # The actual banner is rendered in base.html.j2; nothing to register
    # for M2..M6 because the value is read directly from settings per
    # request in each route's template context.
    return None
