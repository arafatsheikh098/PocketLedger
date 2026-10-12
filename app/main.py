"""Uvicorn entrypoint: ``uvicorn app.main:app``.

This module exists so that the production startup script can import a
``app`` symbol explicitly, and so that side effects (DB creation,
seeding) happen in a single, obvious place.
"""
from __future__ import annotations

import logging

from sqlmodel import Session

from . import create_app
from .config import get_settings
from .db import create_db_and_tables, get_engine

log = logging.getLogger("pocketledger")


def _startup() -> None:
    settings = get_settings()
    create_db_and_tables()
    if settings.seed_on_start:
        # Imported lazily so M1 can run without M7 imports compiled.
        from .demo import ensure_demo_user, seed_demo_data

        with Session(get_engine()) as s:
            u = ensure_demo_user(s)
            seed_demo_data(s, u)


app = create_app()
app.add_event_handler("startup", _startup)
