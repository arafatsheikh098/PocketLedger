"""FastAPI app factory."""
from __future__ import annotations

from fastapi import FastAPI

from .config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fresh FastAPI app.

    ``settings`` is injected by tests. Production code calls
    ``create_app()`` with no arguments.
    """
    if settings is None:
        settings = get_settings()

    if settings.is_production and settings.secret_key.startswith("change-me"):
        raise RuntimeError(
            "SECRET_KEY is the default value. Set a real SECRET_KEY in production."
        )

    app = FastAPI(title="PocketLedger", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


# Module-level app for `uvicorn app:app`. Tests build their own app.
app = create_app()
