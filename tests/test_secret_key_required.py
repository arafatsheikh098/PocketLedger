"""Production refuses to start with the default SECRET_KEY."""
from __future__ import annotations

import pytest


def test_production_rejects_default_secret(monkeypatch) -> None:
    from app import config as cfg
    from app import create_app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", cfg.DEFAULT_SECRET_KEY)
    cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        create_app()


def test_development_allows_default_secret(monkeypatch) -> None:
    from app import config as cfg
    from app import create_app

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", cfg.DEFAULT_SECRET_KEY)
    cfg.get_settings.cache_clear()  # type: ignore[attr-defined]
    app = create_app()
    assert app is not None
